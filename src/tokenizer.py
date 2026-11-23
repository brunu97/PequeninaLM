import json
import time
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer
from tokenizers.decoders import ByteLevel as ByteLevelDecoder
from tokenizers.models import BPE
from tokenizers.pre_tokenizers import ByteLevel
from tokenizers.trainers import BpeTrainer
from transformers import PreTrainedTokenizerFast

BASE = Path(__file__).resolve().parent.parent
DADOS = BASE / "dados_ptpt"
SAIDA = BASE / "tokenizer"

VOCAB = 32000
BLOCO = 1024
BATCH_EFETIVO = 256
PARAMS_MODELO = 50_000_000
MIN_TOKENS = 10
ESPECIAIS = ["<s>", "</s>", "<pad>", "<unk>", "<|im_start|>", "<|im_end|>"]

CHAT_TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>\n' }}"
    "{% endfor %}"
    "{% if add_generation_prompt %}{{ '<|im_start|>assistant\n' }}{% endif %}"
)


def ler_textos(prefixo):
    for ficheiro in sorted(DADOS.glob(f"{prefixo}-*.jsonl")):
        with open(ficheiro, encoding="utf-8") as f:
            for linha in f:
                if not linha.strip():
                    continue
                try:
                    yield json.loads(linha)["text"]
                except (json.JSONDecodeError, KeyError):
                    pass


def treinar_tokenizer():
    textos = list(ler_textos("train")) + list(ler_textos("val"))
    print(f"[tok] {len(textos):,} textos lidos")

    tok = Tokenizer(BPE(unk_token="<unk>"))
    tok.pre_tokenizer = ByteLevel(add_prefix_space=False)
    tok.decoder = ByteLevelDecoder()
    trainer = BpeTrainer(vocab_size=VOCAB, min_frequency=2, special_tokens=ESPECIAIS,
                         initial_alphabet=ByteLevel.alphabet())
    tok.train_from_iterator(textos, trainer=trainer)

    return PreTrainedTokenizerFast(
        tokenizer_object=tok, bos_token="<s>", eos_token="</s>",
        pad_token="<pad>", unk_token="<unk>", chat_template=CHAT_TEMPLATE,
    )


def tokenizar(tok, prefixo):
    # junta todos os textos num fluxo contínuo e corta-o em blocos de tamanho fixo
    pedacos, n_textos, n_tokens = [], 0, 0
    for texto in ler_textos(prefixo):
        ids = tok.encode(texto, add_special_tokens=False)
        if len(ids) < MIN_TOKENS:
            continue
        pedacos.append(np.array([tok.bos_token_id] + ids + [tok.eos_token_id], dtype=np.uint16))
        n_textos += 1
        n_tokens += len(ids) + 2

    fluxo = np.concatenate(pedacos) if pedacos else np.array([], dtype=np.uint16)
    n_blocos = len(fluxo) // BLOCO
    return fluxo[:n_blocos * BLOCO], n_textos, n_tokens, n_blocos


def guardar_bin(caminho, dados):
    mm = np.memmap(caminho, dtype=np.uint16, mode="w+", shape=dados.shape)
    mm[:] = dados
    mm.flush()
    del mm
    print(f"[tok] {caminho.name}: {dados.nbytes / 1e6:.0f} MB")


def main():
    t0 = time.time()
    SAIDA.mkdir(parents=True, exist_ok=True)

    tok = treinar_tokenizer()
    tok.save_pretrained(str(SAIDA))
    n_vocab = len(tok.get_vocab())
    print(f"[tok] vocabulário de {n_vocab:,} tokens guardado em {SAIDA}")

    treino, textos_treino, tokens_treino, blocos_treino = tokenizar(tok, "train")
    validacao, textos_val, tokens_val, blocos_val = tokenizar(tok, "val")
    print(f"[tok] treino: {textos_treino:,} textos, {tokens_treino:,} tokens")
    print(f"[tok] validação: {textos_val:,} textos, {tokens_val:,} tokens")

    guardar_bin(DADOS / "train.bin", treino)
    guardar_bin(DADOS / "val.bin", validacao)

    relatorio = {
        "vocab_size": n_vocab,
        "block_size": BLOCO,
        "train_tokens": tokens_treino,
        "train_blocos": blocos_treino,
        "val_tokens": tokens_val,
        "val_blocos": blocos_val,
        "passos_por_epoca": blocos_treino // BATCH_EFETIVO,
        "tokens_por_param": round(tokens_treino / PARAMS_MODELO, 2),
        "segundos": round(time.time() - t0, 1),
    }
    for destino in (DADOS / "relatorio_tokenizer.json", SAIDA / "relatorio_tokenizer.json"):
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)
    print(json.dumps(relatorio, indent=2))


if __name__ == "__main__":
    main()
