# Automatizar candidaturas a emprego

Candidaturas são o caso difícil da automação de formulários, por três razões que
mudam o desenho da solução:

1. **Submeter é irreversível e visível.** Um bilhete comprado por engano
   devolve-se. Uma candidatura mal preenchida fica no sistema da empresa, com o
   nome da pessoa, e muitas vezes bloqueia recandidaturas à mesma vaga durante
   meses.
2. **Cada plataforma é diferente**, mas são poucas: Greenhouse, Lever, Workday,
   Ashby, SmartRecruiters e Teamtailor cobrem a esmagadora maioria. Vale a pena
   detetar qual é e usar o mapa certo.
3. **Há sempre perguntas específicas da vaga** que nenhum mapa cobre — "porque
   quer trabalhar connosco?", "quantos anos de experiência com Kubernetes?",
   autorização de trabalho, expectativa salarial. Essas são do humano.

Daí a arquitetura recomendada: **o script preenche o que é mecânico, pára no que
é específico, e nunca submete sozinho.**

## A regra do modo por omissão

Por defeito, `submeter = False`. O script preenche tudo o que sabe, tira um
screenshot do formulário completo, lista o que não conseguiu preencher, e deixa
o browser aberto. A pessoa revê, responde às perguntas abertas, e carrega em
Submeter.

Só passa para submissão automática se o utilizador pedir explicitamente e depois
de ter visto pelo menos uma candidatura preenchida por completo. Mesmo aí, vale
a pena manter uma confirmação por candidatura em vez de correr 40 de seguida.

Isto não é excesso de cuidado. É o que separa uma ferramenta que a pessoa usa
durante meses de uma que ela desliga depois do primeiro incidente.

## Detetar a plataforma

A URL chega quase sempre:

| Sinal na URL ou no HTML | Plataforma |
|---|---|
| `boards.greenhouse.io`, `job-boards.greenhouse.io`, iframe `#grnhse_iframe` | Greenhouse |
| `jobs.lever.co` | Lever |
| `myworkdayjobs.com`, `wd1.`/`wd3.`/`wd5.` no host | Workday |
| `jobs.ashbyhq.com` | Ashby |
| `smartrecruiters.com` | SmartRecruiters |
| `teamtailor.com` | Teamtailor |

## Greenhouse

Muitas vezes embebido num iframe dentro do site da empresa. Se `get_by_label`
não encontra campos que estás claramente a ver, é isso:

```python
frame = page.frame_locator("#grnhse_iframe")
frame.get_by_label("First Name").fill(nome)
```

Campos habituais: `First Name`, `Last Name`, `Email`, `Phone`, `Resume/CV`
(upload ou "Enter manually"), `Cover Letter`, `LinkedIn Profile`, `Website`.

O upload aceita `set_input_files` no `input[type=file]`, mesmo escondido. Não
tentes clicar no botão "Attach" — abre um diálogo do sistema operativo que o
Playwright não controla.

Perguntas custom aparecem no fim, como `<select>` ou texto livre, com
`aria-required="true"`. Recolhe as que ficaram vazias e apresenta-as ao humano
em vez de adivinhar.

## Lever

Sem iframe, mais simples. Os campos usam `name` em vez de labels bem ligadas:

```python
page.locator("input[name='name']").fill(nome_completo)
page.locator("input[name='email']").fill(email)
page.locator("input[name='phone']").fill(telefone)
page.locator("input[type='file']").set_input_files(cv_path)
```

As perguntas custom vêm com `name="cards[...]"` — sinal fiável de que são
específicas da vaga e, portanto, do humano.

## Workday

O mais difícil dos três, e o mais comum em empresas grandes.

- **Exige criar conta** antes de candidatar. Faz isso à mão uma vez por empresa
  (cada tenant Workday é uma conta separada) e guarda a sessão no perfil
  persistente. Não tentes automatizar o registo.
- **Wizard de vários passos** com estado guardado no servidor. Se falhar a meio,
  a candidatura fica em rascunho — recuperável, mas confusa.
- **Identifica elementos por `data-automation-id`**, que é estável e é a melhor
  âncora que tens:

```python
page.locator("[data-automation-id='legalNameSection_firstName']").fill(nome)
page.locator("[data-automation-id='bottom-navigation-next-button']").click()
```

- O "Autofill with Resume" faz metade do trabalho sozinho, mas erra muito.
  Deixa-o correr e depois **verifica campo a campo** — é mais rápido do que
  preencher tudo, mas nunca é para confiar às cegas.

## Estrutura de dados do candidato

Mantém o perfil num ficheiro único, fora do código, para não o reescreveres a
cada plataforma. Algo assim:

```json
{
  "nome": "...", "apelido": "...",
  "email": "...", "telefone": "+351...",
  "linkedin": "https://linkedin.com/in/...",
  "github": "...", "website": "...",
  "morada": {"cidade": "...", "pais": "Portugal"},
  "cv_path": "~/docs/CV.pdf",
  "carta_template": "~/docs/carta.md",
  "autorizacao_trabalho": "Cidadão UE, sem necessidade de patrocínio",
  "disponibilidade": "30 dias",
  "expectativa_salarial": null
}
```

Deixa `null` no que varia por vaga. `null` é o sinal de "pergunta ao humano",
que é exatamente o comportamento que queres.

Este ficheiro tem dados pessoais. Fora do repositório, ou no `.gitignore`.

## Cartas de apresentação

Tenta a personalização, mas não finjas. Uma carta gerada que inventa entusiasmo
por uma empresa que o candidato não conhece lê-se à distância e prejudica mais
do que ajuda. O que funciona: um template do próprio candidato com dois ou três
espaços marcados (nome da empresa, o que na vaga liga ao percurso dele), e uma
extração do anúncio para preencher esses espaços. Mostra o resultado antes de
anexar.

Nunca inventes experiência, anos, tecnologias ou formação que não estejam no
perfil. Se a vaga pede algo que o candidato não tem, isso é informação para ele
decidir se se candidata, não algo para o script contornar.

## Checklist antes de dar por concluído

- [ ] O CV anexado é o certo e abriu sem erro (confirma que aparece o nome do
      ficheiro na página, não só que o `set_input_files` não rebentou)
- [ ] Nenhum campo obrigatório ficou vazio — percorre `[aria-required='true']` e
      `[required]` e verifica o valor
- [ ] As perguntas específicas da vaga foram mostradas ao humano
- [ ] Screenshot `full_page=True` do formulário preenchido, antes de submeter
- [ ] O botão Submeter **não** foi clicado, a menos que tenha sido pedido

## Registo das candidaturas

Guarda um CSV ou JSON com data, empresa, vaga, URL, estado e caminho do
screenshot. Serve para não repetir candidaturas, para saber quando fazer
follow-up, e para depurar quando uma plataforma mudar o formulário.

## Limites

Não automatizes contornar verificações anti-bot, não submetas candidaturas em
massa a vagas que não foram lidas, e não uses contas ou identidades que não sejam
do próprio candidato. Além de ser contra os termos de serviço de todas estas
plataformas, é o tipo de coisa que faz as empresas bloquearem o candidato.
