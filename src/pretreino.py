import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    LlamaConfig,
    LlamaForCausalLM,
    PreTrainedTokenizerFast,
    Trainer,
    TrainingArguments,
    set_seed,
)

BASE = Path(__file__).resolve().parent.parent
DADOS = BASE / "dados_ptpt"
SAIDA = BASE / "modelos" / "pequeninalm-base"

BLOCO = 1024
BATCH = 64
ACUMULACAO = 4  # batch efetivo de 64 x 4 = 256
LR = 1e-3


class Blocos(Dataset):
    def __init__(self, caminho):
        self.tokens = np.memmap(caminho, dtype=np.uint16, mode="r")

    def __len__(self):
        return len(self.tokens) // BLOCO

    def __getitem__(self, i):
        bloco = self.tokens[i * BLOCO:(i + 1) * BLOCO]
        ids = torch.from_numpy(bloco.astype(np.int64))
        return {"input_ids": ids, "labels": ids.clone()}


def escolher_epocas():
    with open(DADOS / "relatorio_tokenizer.json", encoding="utf-8") as f:
        tokens_por_param = json.load(f)["tokens_por_param"]

    # com poucos dados compensa dar mais voltas ao corpus
    if tokens_por_param < 10:
        return tokens_por_param, 8.0
    if tokens_por_param < 20:
        return tokens_por_param, 4.0
    return tokens_por_param, 2.0


def criar_modelo():
    config = LlamaConfig(
        vocab_size=32000,
        hidden_size=512,
        intermediate_size=1408,
        num_hidden_layers=12,
        num_attention_heads=8,
        num_key_value_heads=4,
        max_position_embeddings=BLOCO,
        tie_word_embeddings=True,
    )
    return LlamaForCausalLM(config)


def main():
    set_seed(42)
    SAIDA.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    tokens_por_param, epocas = escolher_epocas()
    print(f"[pretreino] {tokens_por_param} tokens por parâmetro, {epocas:g} épocas, batch {BATCH}x{ACUMULACAO}")

    model = criar_modelo()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[pretreino] modelo com {n_params / 1e6:.1f}M parâmetros")

    treino = Blocos(DADOS / "train.bin")
    validacao = Blocos(DADOS / "val.bin")
    print(f"[pretreino] {len(treino):,} blocos para treino e {len(validacao):,} para validação")

    tok = PreTrainedTokenizerFast.from_pretrained(str(BASE / "tokenizer"))

    cuda = torch.cuda.is_available()
    bf16 = cuda and torch.cuda.is_bf16_supported()
    # torch.compile e workers do dataloader dão problemas no Windows
    linux = sys.platform.startswith("linux")

    args = TrainingArguments(
        output_dir=str(SAIDA), overwrite_output_dir=True,
        num_train_epochs=epocas,
        per_device_train_batch_size=BATCH, per_device_eval_batch_size=BATCH,
        gradient_accumulation_steps=ACUMULACAO, learning_rate=LR,
        lr_scheduler_type="cosine", warmup_ratio=0.02, weight_decay=0.1,
        max_grad_norm=1.0, bf16=bf16, fp16=cuda and not bf16,
        torch_compile=cuda and linux, dataloader_num_workers=4 if linux else 0,
        logging_steps=50, eval_strategy="steps", eval_steps=250,
        save_steps=500, save_total_limit=3, report_to=[], seed=42,
    )
    trainer = Trainer(model=model, args=args, train_dataset=treino, eval_dataset=validacao)

    retomar = any(SAIDA.glob("checkpoint-*"))
    print(f"[pretreino] a treinar (cuda={cuda}, bf16={bf16})" + (", a continuar do último checkpoint" if retomar else ""))
    trainer.train(resume_from_checkpoint=retomar or None)

    trainer.save_model(str(SAIDA))
    tok.save_pretrained(str(SAIDA))
    loss = trainer.evaluate()["eval_loss"]
    perplexidade = math.exp(loss)
    segundos = time.time() - t0
    print(f"[pretreino] eval_loss={loss:.4f}, perplexidade={perplexidade:.2f}")
    print(f"[pretreino] guardado em {SAIDA} ({segundos:.0f}s)")

    with open(SAIDA / "relatorio_pretreino.json", "w", encoding="utf-8") as f:
        json.dump({"params": n_params, "epocas": epocas, "eval_loss": loss,
                   "perplexidade": round(perplexidade, 2), "segundos": round(segundos, 1)},
                  f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
