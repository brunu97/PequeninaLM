import importlib.util
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent

FASES = {
    "tokenizer": SRC / "tokenizer.py",
    "pretreino": SRC / "pretreino.py",
    "sft": SRC / "sft.py",
}


def carregar(caminho):
    spec = importlib.util.spec_from_file_location(caminho.stem, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main():
    pedidas = sys.argv[1:]
    for nome in pedidas:
        if nome not in FASES:
            sys.exit(f"Fase desconhecida: {nome} (válidas: {', '.join(FASES)})")

    t0 = time.time()
    for nome, caminho in FASES.items():
        if pedidas and nome not in pedidas:
            continue
        print(f"\n{'=' * 50}\n  {nome}\n{'=' * 50}", flush=True)
        carregar(caminho).main()
        print(f"  {nome} concluído ({time.time() - t0:.0f}s no total)", flush=True)

    print(f"\nPequeninaLM criada em {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
