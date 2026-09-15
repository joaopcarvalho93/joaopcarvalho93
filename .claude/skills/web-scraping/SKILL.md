---
name: web-scraping
description: >-
  Playbook para scraping e automação de browser com Playwright em sites reais
  que exigem login, formulários com JavaScript reativo, banners de cookies e
  passos irreversíveis. Usa esta skill sempre que a tarefa envolva extrair dados
  de um site, preencher um formulário automaticamente, vigiar uma página à espera
  de que algo mude (stock, vagas, lugares, preços), submeter candidaturas a
  emprego, ou automatizar qualquer fluxo web multi-passo — incluindo quando o
  utilizador só diz "faz scraping", "automatiza este site", "preenche isto por
  mim", "vigia esta página", "candidaturas automáticas", "scrape this site",
  "fill this form", "monitor this page", ou cola um URL e pede dados de lá.
  Usa-a também quando um script de automação existente está a falhar de forma
  intermitente — a maior parte das causas está documentada aqui.
---

# Scraping e automação web que aguenta sites reais

Automação web falha quase sempre pelas mesmas razões: o seletor era frágil, o
campo tinha JavaScript que ignorou o `fill()`, o botão estava visível mas
desativado, a sessão expirou, ou o script continuou alegremente depois de já ter
saído do caminho previsto. Este playbook existe para eliminar essas causas.

A regra que orienta tudo o resto: **automatiza o que é repetitivo e reversível,
e entrega ao humano o que é ambíguo ou irreversível.** Um script que pára e
grita é infinitamente melhor do que um que submete a coisa errada.

## Antes de escrever código

**1. Verifica se precisas mesmo de um browser.** Abre as DevTools no separador
Network, faz a ação à mão e vê o que o site chama. Muitos sites que parecem
exigir browser estão a falar com uma API JSON que podes chamar diretamente com
`httpx`. Isso é 50x mais rápido, não parte com mudanças de CSS, e não consome
memória. Só passa para Playwright quando há login com estado, renderização por
JS, ou proteção anti-bot que a chamada direta não aguenta.

**2. Grava o fluxo à mão uma vez.** `playwright codegen <url>` abre um browser e
escreve o código enquanto clicas. Não copies o resultado tal e qual — os
seletores que ele gera são muitas vezes frágeis — mas usa-o para descobrir os
nomes acessíveis reais dos elementos, que é o que te interessa. É muito mais
rápido do que adivinhar seletores.

**3. Pergunta-te o que acontece quando corre mal no pior momento possível.**
Desenha a política de erro antes do código feliz. Ver "Política de erro em duas
fases" abaixo.

**4. Verifica se é legítimo.** `robots.txt`, termos de serviço, e o bom senso.
Automatizar o que o utilizador faria à mão na conta dele é uma coisa; contornar
captchas, criar contas falsas, martelar um servidor ou raspar dados pessoais de
terceiros é outra. Se a tarefa for do segundo tipo, di-lo em vez de a fazer.

## Sessão e login: não automatizes o login

A tentação é guardar utilizador e password e fazer o script escrevê-los. Isso
parte com 2FA, com captcha, com deteção de bot, e obriga-te a ter credenciais em
disco. A alternativa é melhor em todos os eixos:

```python
browser = p.chromium.launch_persistent_context(
    user_data_dir="./perfil_browser",   # cookies e sessão ficam aqui
    headless=False,
)
page = browser.pages[0] if browser.pages else browser.new_page()
page.goto(url)
input(">>> Faz login na janela do browser. Quando estiveres dentro, prime Enter: ")
```

O humano faz login uma vez, à mão. A partir daí o perfil guarda a sessão e as
execuções seguintes já entram autenticadas. Custa 20 segundos na primeira vez e
poupa-te todo o combate contra a autenticação.

Duas consequências a respeitar: a pasta do perfil contém a sessão iniciada do
utilizador, por isso nunca a envies, commites ou partilhes — mete-a no
`.gitignore` logo. E verifica sempre se a sessão ainda é válida antes de
assumir que estás autenticado (se a URL saltar para `/login` ou `/autenticacao`,
a sessão expirou e isso é um erro que exige o humano, não um retry).

Segredos que o utilizador te dá em runtime (número de passe, NIF, token) ficam
só em memória. Não os escrevas em ficheiros de configuração, não os metas em
logs, não os ponhas em screenshots que vais guardar.

## Localizar elementos

Ordena as tuas tentativas da mais estável para a mais frágil. Os nomes acessíveis
mudam muito menos do que classes CSS, porque estão ligados ao que o utilizador vê:

1. `page.get_by_role("button", name=re.compile("Continuar", re.I))`
2. `page.get_by_label(re.compile("Email|E-mail", re.I))`
3. `page.get_by_placeholder(re.compile("Origem", re.I))`
4. `page.get_by_text("Confirmar", exact=True)`
5. `page.locator("[data-testid='submit']")`
6. CSS/XPath — último recurso, e comenta porquê

Usa **regex em vez de strings exactas** nos nomes. O nome acessível real é
muitas vezes maior do que o texto visível — um botão que mostra "Comprar" pode
chamar-se "Comprar esta viagem (abre nova janela modal)". `re.compile("Comprar")`
apanha os dois; `name="Comprar"` falha.

**iframes**: se o `get_by_role` não encontra nada que claramente está no ecrã, o
elemento está provavelmente dentro de um iframe. Formulários de candidatura
(Greenhouse, Lever) e widgets de pagamento vivem quase sempre em iframes.

```python
frame = page.frame_locator("iframe[title*='Application']")
frame.get_by_label("First name").fill("...")
```

## Escrever em campos: escreve e confirma

`fill()` define o valor por baixo do capô. Campos com JavaScript reativo (React,
Vue, autocompletes) muitas vezes não reparam e o site continua a achar que o
campo está vazio — o botão Avançar fica cinzento e não percebes porquê.

```python
campo.click()
campo.fill("")             # limpar
campo.type(valor, delay=50) # simula teclas reais, dispara os eventos
campo.press("Tab")          # dispara o blur/validação
if (campo.input_value() or "").strip() != valor:
    raise RuntimeError(f"O campo não registou o valor: {valor}")
```

A verificação no fim não é paranoia. É o que transforma uma falha silenciosa
(que só descobres três passos à frente, com uma mensagem inútil) numa falha que
te diz exatamente o que aconteceu.

**Autocompletes** precisam de dois tempos: escrever, esperar pela sugestão, e
clicar na sugestão. Se clicares antes de a lista aparecer, apanhas o item errado.
Fallback quando a lista não é clicável: `ArrowDown` + `Enter`.

## Esperar: por estado, nunca por tempo

`time.sleep()` a torcer para que a página tenha carregado é a causa número um de
testes intermitentes. O Playwright já espera automaticamente pelos elementos;
aproveita isso e espera por condições explícitas quando precisas de mais.

A subtileza que apanha toda a gente: **visível não é o mesmo que ativo**. Um
botão desativado está lá, é visível, e o `click()` do Playwright fica à espera
dele até rebentar com um timeout confuso. Na prática, botão desativado quer quase
sempre dizer "há um campo obrigatório por preencher que tu não viste".

```python
def clicar_quando_ativo(locator, descricao, timeout_ms=25000):
    limite = time.time() + timeout_ms / 1000
    while time.time() < limite:
        try:
            if locator.is_visible() and locator.is_enabled():
                locator.click()
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise PrecisaDeHumano(
        f"O botão '{descricao}' ficou desativado — o site deve estar à espera "
        f"de um campo que não foi preenchido.")
```

Repara que o timeout levanta um erro que *explica a causa provável*, não um
`TimeoutError` genérico. Quem lê o log às 3 da manhã agradece.

## Deixa o site construir as URLs

Quando um site tem URLs com IDs internos (`?origem=94-2006&destino=94-3011`),
não faças engenharia reversa desses IDs. Preenche o formulário uma vez, deixa o
site resolver os IDs, apanha a URL de resultados, e a partir daí muda só o
parâmetro que te interessa:

```python
url = page.url  # já com os IDs certos
url = re.sub(r"startDate=\d{4}-\d{2}-\d{2}", f"startDate={ano}-{mes}-{dia}", url)
```

Ganhas duas coisas: não partes quando o site muda a codificação dos IDs, e as
iterações seguintes do teu ciclo de vigia saltam o formulário todo — vão direitas
aos resultados.

## Política de erro em duas fases

Este é o padrão mais importante do playbook e o que se transfere para qualquer
projeto. A ideia: **o mesmo erro tem gravidades diferentes conforme a altura em
que acontece.**

- **Fase de vigia** (ainda não aconteceu nada de irreversível): o site abanou, a
  rede caiu, um seletor não apareceu. Regista, tira screenshot, continua o ciclo.
  Interromper aqui seria pior do que o erro.
- **Fase crítica** (já estás a meio de algo que não se desfaz — comprar,
  submeter, pagar, apagar): qualquer erro pára tudo, faz barulho, e deixa o
  browser aberto exatamente no passo onde parou para o humano acabar à mão. Nunca
  tentes recuperar sozinho a meio de uma transação.

Implementa a distinção com uma exceção própria, para que a intenção fique no
código e não só na tua cabeça:

```python
class PrecisaDeHumano(Exception):
    """Erro na fase crítica: exige intervenção imediata, não retry."""
```

```python
while True:
    try:
        if condicao_encontrada(page):
            try:
                concluir(page, cfg)          # fase crítica
                alertar("Concluído com sucesso.")
            except Exception as e:
                page.screenshot(path="erro_fase_critica.png", full_page=True)
                alertar(f"PRECISO DE TI: {e}\n\nO browser está aberto no passo "
                        f"onde parou. Acaba à mão AGORA.")
            break
        time.sleep(INTERVALO)
    except Exception as e:                   # fase de vigia
        log(f"Erro transitório ({type(e).__name__}: {e}). Continuo.")
        page.screenshot(path="erro_vigia.png", full_page=True)
        time.sleep(INTERVALO)
```

O alerta tem de ser impossível de ignorar se o utilizador não está a olhar para o
ecrã: som, notificação do sistema, ou uma mensagem que fique. Um `print` não
chega.

## Ações irreversíveis precisam de uma barreira

Comprar, submeter uma candidatura, enviar uma mensagem, apagar. Por defeito, para
antes do clique final, mostra ao utilizador o que vai acontecer, e espera
confirmação. Só automatiza o passo final quando o utilizador o pediu
explicitamente e o custo de errar é baixo — e mesmo aí, um dry-run que preenche
tudo e pára antes de submeter deve ser o modo por omissão.

## Ruído do site

**Banners de cookies** tapam elementos e fazem os cliques falharem com erros que
não fazem sentido. Trata-os com uma cascata: rejeitar → aceitar → remover o nó
por JavaScript. Ver `aceitar_cookies()` no toolkit.

**Redirects** do próprio site interrompem o `goto()` do Playwright e levantam
exceções mesmo quando a navegação correu bem. Navega com retry e confirma o
destino pela URL, não pelo facto de o `goto` não ter rebentado. Ver `ir_para()`.

**Modais e overlays** que aparecem a meio: se um clique falhar com "element is
not visible" ou "intercepts pointer events", há algo por cima. Procura o modal
antes de andares à luta com o seletor.

## Depurar

Quando alguma coisa falha, o que te salva é ver o que o browser via naquele
momento. Guarda sempre um screenshot **e** o HTML:

```python
page.screenshot(path="erro.png", full_page=True)
open("erro.html", "w", encoding="utf-8").write(page.content())
```

Outras ferramentas, por ordem de utilidade:

- `headless=False` durante o desenvolvimento. Vê o que se passa.
- `PWDEBUG=1 python script.py` — abre o inspector do Playwright, passo a passo.
- `page.pause()` — pára ali e deixa-te explorar seletores no inspector.
- Tracing para correr sem supervisão: `context.tracing.start(screenshots=True,
  snapshots=True)` e depois `stop(path="trace.zip")`, que abres com
  `playwright show-trace trace.zip`.

## Ser educado com o servidor

Intervalos entre pedidos na ordem dos 20–60 segundos para vigia contínua. Nunca
paralelizes dezenas de pedidos contra o mesmo site. Se o site devolver 429 ou
403, aumenta o intervalo em vez de tentares disfarçar-te. Um script que
sobrecarrega um site público é um problema, não uma vitória técnica.

## Ficheiros desta skill

- `scripts/toolkit.py` — helpers genéricos e testados, prontos a copiar para um
  projeto novo: `ir_para`, `aceitar_cookies`, `escrever_e_confirmar`,
  `clicar_quando_ativo`, `escolher_dropdown`, `guardar_diagnostico`, `alertar`,
  `manter_pc_acordado`. Começa por aqui em vez de reescrever isto do zero.
- `references/candidaturas.md` — aplicar tudo isto a candidaturas a emprego:
  Greenhouse, Lever, Workday, upload de CV, e a regra de nunca submeter sozinho.
  Lê quando a tarefa for sobre candidaturas ou formulários longos.
- `references/extraccao.md` — o outro lado do problema: extrair dados em escala
  (paginação, tabelas, APIs internas, exportar para CSV/JSON, retomar de onde
  parou). Lê quando o objetivo for recolher dados, não preencher formulários.
