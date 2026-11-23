<p align="center">
  <img src="logo-pequenina-lm.svg" alt="PequeninaLM" width="480"/>
</p>

<p align="center">
  <b>Um modelo de linguagem pequeno em Português de Portugal</b><br/>
  <sub>50M</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/PT--PT-Portugal-006600?style=for-the-badge" alt="PT-PT"/>
  <img src="https://img.shields.io/badge/parâmetros-52M-1f6feb?style=for-the-badge" alt="52M parâmetros"/>
  <img src="https://img.shields.io/badge/contexto-1024-2da44e?style=for-the-badge" alt="contexto 1024"/>
  <img src="https://img.shields.io/badge/arquitetura-Llama-f08000?style=for-the-badge" alt="Llama"/>
  <img src="https://img.shields.io/badge/licença-MIT-cc0000?style=for-the-badge" alt="MIT"/>
</p>

<p align="center">
  <a href="https://huggingface.co/brunuu/PequeninaLM"><img src="https://img.shields.io/badge/🤗_Hugging_Face-brunuu%2FPequeninaLM-ffcc4d?style=for-the-badge" alt="Hugging Face"/></a>
</p>

<br/>

## O que é

A PequeninaLM é um modelo de linguagem com cerca de 52 milhões de parâmetros, treinado do zero e só em português de Portugal. Leu a Wikipédia convertida para PT-PT e aprendeu a conversar com 80 mil conversas escritas de raiz em português europeu.

Aqui está o código para a treinar, os prompts usados para gerar as conversas e o modelo em GGUF. A versão para usar com o `transformers`, os exemplos e os detalhes do treino estão no [Hugging Face](https://huggingface.co/brunuu/PequeninaLM).

| | |
|:--|:--|
| **Arquitetura** | Llama com 12 camadas e 51,8 milhões de parâmetros |
| **Pré-treino** | 275 milhões de tokens da Wikipédia, 2h27 numa A100 |
| **SFT** | 80 000 conversas, 34 minutos numa RX 7800 XT |

<br/>

## Experimentar

Abre um dos ficheiros da pasta `gguf/` no LM Studio, ou corre no llama.cpp:

```bash
llama-cli -m gguf/pequeninalm-f16.gguf
```

Ou em Python, com o modelo do [Hugging Face](https://huggingface.co/brunuu/PequeninaLM):

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

tok = AutoTokenizer.from_pretrained("brunuu/PequeninaLM")
model = AutoModelForCausalLM.from_pretrained("brunuu/PequeninaLM")

msgs = [{"role": "user", "content": "Olá! Quem és tu?"}]
ids = tok.apply_chat_template(msgs, return_tensors="pt", add_generation_prompt=True)
out = model.generate(ids, max_new_tokens=100, do_sample=True, temperature=0.7, top_p=0.9)
print(tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True))
```

<br/>

## O que vem no repositório

```
├── gguf/
│   ├── pequeninalm-f16.gguf         o modelo para llama.cpp, LM Studio e Ollama
│   └── pequeninalm-q8_0.gguf        o mesmo a 8 bits, com metade do tamanho
├── prompts/
│   ├── conversas_curtas.md          prompt para as conversas de uma volta
│   └── conversas_longas.md          prompt para as conversas longas, identidade e desabafos
└── src/
    ├── Criar_PequeninaLM.py         corre as fases todas por ordem
    ├── tokenizer.py                 treina o tokenizer e tokeniza o corpus
    ├── pretreino.py                 pré-treino do modelo base
    └── sft.py                       ensina o modelo a conversar
```

<br/>

## Destilação com DeepSeek

Depois do pré-treino, o modelo só sabe continuar texto. Para aprender a conversar tem de ver muitos exemplos de perguntas e respostas, e há poucas conversas escritas em português de Portugal. A maioria está em português do Brasil ou foi traduzida do inglês.

Por isso pedi ao DeepSeek que as escrevesse, e os prompts da pasta `prompts/` são as instruções que lhe dei.

Isto é destilação. Um modelo grande, o professor, escreve as respostas e o modelo pequeno, o aluno, aprende a imitá-las. Neste caso o professor é o DeepSeek e a aluna é a PequeninaLM, que treina com as 80 mil conversas que ele escreveu. Não vê os pesos nem as probabilidades do DeepSeek, só o texto final.

Os prompts foram escritos a pensar no tamanho do modelo. Um modelo com 52 milhões de parâmetros aprende sobretudo padrões e, se muitas respostas começarem com «Boa pergunta», passa a dizer «Boa pergunta» a tudo. Os prompts pedem respostas curtas que respondem logo na primeira frase, em português de Portugal e sem frases feitas. Dizem também ao DeepSeek quem é a PequeninaLM, para ela saber o seu nome e não se apresentar como outro modelo.

- `conversas_curtas.md` dá origem a conversas de uma volta: cumprimentos, factos, definições, conselhos, opiniões, dúvidas de português de Portugal, perguntas a que o modelo não pode responder e pedidos que deve recusar.
- `conversas_longas.md` segue as mesmas regras e acrescenta conversas de 3 ou 4 voltas em que o utilizador volta ao que já disse, perguntas sobre a identidade do modelo a meio da conversa e desabafos.

<br/>

## Como recriar o modelo

Os dados não vêm no repositório. Antes de treinar tens de preparar duas pastas.

**`dados_ptpt/`** com o texto do pré-treino, em ficheiros `train-*.jsonl` e `val-*.jsonl`, um artigo por linha no formato `{"text": "..."}`. Eu usei a Wikipédia em português (`wikimedia/wikipedia`, versão 20231101.pt). Tirei os artigos escritos sobretudo em português do Brasil, converti os restantes para PT-PT e limpei as referências, as predefinições e os artigos demasiado curtos.

**`dados_sft/`** com as conversas, em ficheiros `.jsonl`, uma por linha no formato `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}`. Gerei-as com a API do DeepSeek usando os prompts da pasta `prompts/`, em lotes de 40 com temas, nomes e terras escolhidos ao acaso. Cada conversa passou por um validador que deita fora palavras do Brasil, gerúndio, acentos em falta, frases feitas, respostas longas demais e perguntas repetidas.

Com as duas pastas prontas:

```bash
pip install -r requirements.txt
python src/Criar_PequeninaLM.py
```

Treina o tokenizer, faz o pré-treino e no fim o SFT. O pré-treino precisa de uma GPU a sério. O SFT corre bem numa placa de jogos.

<br/>

## Créditos

**Wikipédia.** Todo o conhecimento do modelo vem dos artigos da [Wikipédia em português](https://pt.wikipedia.org), escritos por milhares de voluntários, sob a licença [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/deed.pt).

**Twemoji.** A mão do logótipo é o emoji 🤏 do [Twemoji](https://github.com/jdecked/twemoji), © Twitter, Inc. e outros contribuidores, usado sob a licença [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.pt).

## Licença

MIT. Podes usar, alterar e distribuir à vontade, incluindo em projetos comerciais.
