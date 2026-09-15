# Extrair dados em escala

O playbook principal trata de *agir* num site. Este trata do outro lado:
*recolher* dados. As prioridades mudam — aqui o que importa é velocidade,
retomar de onde parou, e não sobrecarregar o servidor.

## Procura a API antes de abrir um browser

Este é o passo que a maior parte das pessoas salta e é quase sempre o que decide
se o projeto demora uma hora ou dois dias.

Abre as DevTools, separador Network, filtra por Fetch/XHR, e faz a ação à mão
(pesquisar, mudar de página, abrir um detalhe). Se aparecer uma resposta JSON com
os dados que queres, ganhaste:

- `httpx` em vez de Playwright: cerca de 50x mais rápido, sem browser na memória
- não parte quando o CSS muda
- paginação normalmente por parâmetro simples (`?page=2`, `?offset=40`)
- a resposta traz muitas vezes campos que o site nem mostra

Copia o pedido com "Copy as cURL" e converte. Mantém os headers que interessam
(`Authorization`, `Cookie`, `User-Agent`, `Referer`); descarta o resto e vê se
continua a funcionar.

Sinais de que vais mesmo precisar de browser: conteúdo que só aparece depois de
scroll, tokens gerados por JavaScript a cada pedido, proteção Cloudflare/Datadome
ativa, ou dados espalhados por HTML renderizado no cliente sem chamada JSON.

## Paginação

Três padrões, por ordem de robustez:

**Cursor/token** (`?cursor=abc123`) — o melhor. Segue o cursor da resposta até
ele vir vazio. Não duplica nem salta itens se a lista mudar a meio.

**Offset/página** (`?page=2`) — funciona, mas se a lista for reordenada enquanto
raspas, podes duplicar ou perder registos. Deduplica sempre por ID no fim.

**Scroll infinito** — precisa de browser. Faz scroll, espera que o número de
itens aumente, repete. Pára quando o número deixa de crescer entre duas
iterações, não quando "parece que acabou":

```python
anterior = 0
while True:
    page.mouse.wheel(0, 20000)
    page.wait_for_timeout(1500)
    atual = page.locator("[data-item]").count()
    if atual == anterior:
        break
    anterior = atual
```

## Retomar de onde parou

Qualquer recolha que demore mais de uns minutos vai ser interrompida — rede,
rate limit, o portátil que fecha. Grava incrementalmente em vez de acumular tudo
em memória e escrever no fim:

- **JSONL** (um objeto JSON por linha) é o formato certo para isto: acrescentas
  linhas à medida que vais, e um ficheiro truncado a meio continua legível.
- Guarda os IDs já processados num `set` carregado do ficheiro no arranque, e
  salta-os. Retomar passa a ser trivial e podes correr o script as vezes que
  quiseres sem duplicar.
- Converte para CSV/Excel no fim, como passo separado.

```python
vistos = set()
if os.path.exists("dados.jsonl"):
    with open("dados.jsonl", encoding="utf-8") as fh:
        vistos = {json.loads(l)["id"] for l in fh if l.strip()}

with open("dados.jsonl", "a", encoding="utf-8") as fh:
    for item in items:
        if item["id"] in vistos:
            continue
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        fh.flush()
```

## Tabelas HTML

Para tabelas simples, `pandas.read_html(page.content())` resolve em uma linha.
Para tabelas com células compostas, links que interessam, ou cabeçalhos em várias
linhas, extrai à mão com locators — o pandas deita fora tudo o que não seja texto.

## Ritmo e educação

- Intervalo entre pedidos: 1–3 segundos para recolhas, 20–60 para vigia contínua.
- Nunca paralelizes dezenas de pedidos contra o mesmo domínio. Dois ou três
  workers no máximo, e só se o site for grande.
- **429 ou 403 é um sinal, não um obstáculo.** Aumenta o intervalo, faz backoff
  exponencial, e se persistir, pára. Rodar user-agents e IPs para contornar um
  bloqueio explícito é ultrapassar a linha entre automatizar e atacar.
- Respeita o `robots.txt`. `urllib.robotparser` lê-o em três linhas.
- Identifica-te no User-Agent quando for um projeto teu e não houver razão para o
  esconder.

## Dados pessoais

Se o que estás a recolher inclui nomes, emails, moradas ou perfis de pessoas,
isso é RGPD. Recolhe o mínimo necessário, guarda-o em local privado, e não o
publiques nem o commites. "Estava público na internet" não é base legal para
processar dados pessoais em escala.

## Validar o que recolheste

Antes de dar o trabalho por feito, verifica o óbvio: o número de registos bate
certo com o que o site dizia ter? Há campos vazios em massa (sinal de seletor
errado, não de dados em falta)? Os tipos fazem sentido — datas parseadas, números
como números, acentos corretos (`ensure_ascii=False`, `encoding="utf-8"`)?

Uma recolha silenciosamente meia errada é pior do que uma que rebentou.
