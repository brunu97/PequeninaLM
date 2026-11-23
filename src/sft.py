#!/usr/bin/env python3
import json
import random
import time
from functools import partial
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, set_seed

BASE = Path(__file__).resolve().parent.parent
MODELO_BASE = BASE / "modelos" / "pequeninalm-base"
DADOS = BASE / "dados_sft"
SAIDA = BASE / "modelos" / "pequeninalm-chat"

MAX_TOKENS = 1024
EPOCAS = 3.0
LR = 2e-4
IGNORAR = -100


class Conversas(Dataset):
    def __init__(self, conversas, tok):
        self.conversas = conversas
        self.tok = tok
        self.inicio = tok.convert_tokens_to_ids("<|im_start|>")
        self.fim = tok.convert_tokens_to_ids("<|im_end|>")
        self.assistente = tok.encode("assistant\n", add_special_tokens=False)

    def __len__(self):
        return len(self.conversas)

    def __getitem__(self, i):
        texto = self.tok.apply_chat_template(self.conversas[i], tokenize=False)
        ids = self.tok.encode(texto, add_special_tokens=False, truncation=True, max_length=MAX_TOKENS)
        labels = [IGNORAR] * len(ids)

        n = len(self.assistente)
        j, na_resposta = 0, False
        while j < len(ids):
            if ids[j] == self.inicio and ids[j + 1:j + 1 + n] == self.assistente:
                na_resposta = True
                j += 1 + n
                continue
            if na_resposta:
                # o <|im_end|> também conta, senão o modelo nunca aprende a parar
                labels[j] = ids[j]
                na_resposta = ids[j] != self.fim
            j += 1

        return {"input_ids": torch.tensor(ids), "labels": torch.tensor(labels)}


def juntar(lote, pad):
    comprimento = max(len(x["input_ids"]) for x in lote)
    ids = torch.full((len(lote), comprimento), pad, dtype=torch.long)
    labels = torch.full((len(lote), comprimento), IGNORAR, dtype=torch.long)
    mascara = torch.zeros((len(lote), comprimento), dtype=torch.long)
    for i, x in enumerate(lote):
        n = len(x["input_ids"])
        ids[i, :n] = x["input_ids"]
        labels[i, :n] = x["labels"]
        mascara[i, :n] = 1
    return {"input_ids": ids, "labels": labels, "attention_mask": mascara}


def ler_conversas():
    conversas = []
    for ficheiro in sorted(DADOS.glob("*.jsonl")):
        with open(ficheiro, encoding="utf-8") as f:
            for linha in f:
                try:
                    conversas.append(json.loads(linha)["messages"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return conversas


def main():
    set_seed(42)
    SAIDA.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    cuda = torch.cuda.is_available()
    bf16 = cuda and torch.cuda.is_bf16_supported()
    tok = AutoTokenizer.from_pretrained(str(MODELO_BASE))
    model = AutoModelForCausalLM.from_pretrained(
        str(MODELO_BASE), torch_dtype=torch.bfloat16 if cuda else torch.float32)
    model.config.use_cache = False

    conversas = ler_conversas()
    random.Random(42).shuffle(conversas)
    n_val = max(1, len(conversas) // 10)
    treino = Conversas(conversas[:-n_val], tok)
    validacao = Conversas(conversas[-n_val:], tok)
    print(f"[sft] {len(conversas):,} conversas, {len(treino):,} para treino e {len(validacao):,} para validação")

    args = TrainingArguments(
        output_dir=str(SAIDA), overwrite_output_dir=True,
        num_train_epochs=EPOCAS,
        per_device_train_batch_size=32, per_device_eval_batch_size=32,
        gradient_accumulation_steps=1, learning_rate=LR,
        lr_scheduler_type="cosine", warmup_ratio=0.03, weight_decay=0.01,
        max_grad_norm=1.0, bf16=bf16, logging_steps=10,
        eval_strategy="steps", eval_steps=250, save_steps=250,
        save_total_limit=2, report_to=[], seed=42,
        load_best_model_at_end=True, metric_for_best_model="eval_loss",
    )
    pad = tok.pad_token_id if tok.pad_token_id is not None else 2
    trainer = Trainer(model=model, args=args, train_dataset=treino, eval_dataset=validacao,
                      data_collator=partial(juntar, pad=pad))

    retomar = any(SAIDA.glob("checkpoint-*"))
    print(f"[sft] a treinar {EPOCAS:g} épocas" + (", a continuar do último checkpoint" if retomar else ""))
    trainer.train(resume_from_checkpoint=retomar or None)

    tok.eos_token = "<|im_end|>"
    for config in (model.config, model.generation_config):
        config.bos_token_id = tok.bos_token_id
        config.eos_token_id = tok.eos_token_id
        config.pad_token_id = pad
    trainer.save_model(str(SAIDA))
    tok.save_pretrained(str(SAIDA))
    loss = trainer.evaluate()["eval_loss"]
    segundos = time.time() - t0
    print(f"[sft] eval_loss={loss:.4f}, guardado em {SAIDA} ({segundos:.0f}s)")

    with open(SAIDA / "relatorio_sft.json", "w", encoding="utf-8") as f:
        json.dump({"exemplos": len(conversas), "epocas": EPOCAS, "eval_loss": loss,
                   "segundos": round(segundos, 1)}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
