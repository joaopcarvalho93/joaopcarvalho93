# Como usar esta skill noutros projetos

Três formas, da mais prática para a mais manual.

## 1. Instalar no perfil (fica disponível em todos os projetos)

Copia a pasta para as skills pessoais do Claude Code:

```bash
cp -r .claude/skills/web-scraping ~/.claude/skills/
```

A partir daí a skill ativa-se sozinha em qualquer projeto quando pedires
scraping, automação de formulários, vigia de páginas ou candidaturas. Não é
preciso invocá-la pelo nome.

## 2. Copiar para um projeto específico

```bash
mkdir -p <projeto>/.claude/skills
cp -r web-scraping <projeto>/.claude/skills/
```

Útil quando queres que a skill acompanhe o repositório e fique disponível para
quem clonar o projeto.

## 3. Ficheiro `.skill`

O ficheiro `web-scraping.skill` (é um zip) instala-se a partir da interface do
Claude, com o botão **Save skill**. Conveniente para partilhar com outra pessoa.

---

## Arrancar um projeto novo com isto

```bash
pip install playwright
playwright install chromium
cp ~/.claude/skills/web-scraping/scripts/toolkit.py .
echo "perfil_browser/" >> .gitignore
echo "diagnostico/" >> .gitignore
```

A pasta do perfil contém a sessão iniciada nos sites. Nunca a commites nem a
partilhes — daí a linha no `.gitignore` fazer parte do arranque e não ser algo
para lembrar depois.
