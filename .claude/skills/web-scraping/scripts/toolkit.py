# -*- coding: utf-8 -*-
"""
Toolkit de automação web com Playwright.

Helpers genéricos para os problemas que aparecem sempre em sites reais:
navegação instável, banners de cookies, campos com JavaScript reativo, botões
desativados, dropdowns custom, e diagnóstico quando algo corre mal.

Copia este ficheiro para o projeto e importa o que precisares. Não tem estado
global nem depende de nenhum site em particular.

Requisitos:
    pip install playwright
    playwright install chromium

Uso típico:

    from playwright.sync_api import sync_playwright
    from toolkit import (abrir_browser, ir_para, aceitar_cookies,
                         escrever_e_confirmar, clicar_quando_ativo,
                         guardar_diagnostico, alertar, PrecisaDeHumano)

    with sync_playwright() as p:
        browser, page = abrir_browser(p, "./perfil_browser")
        ir_para(page, "https://exemplo.pt")
        aceitar_cookies(page)
        ...
"""

from __future__ import annotations

import os
import platform
import re
import sys
import time
from datetime import datetime
from typing import Optional

from playwright.sync_api import Locator, Page, TimeoutError as PWTimeout


# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------

class PrecisaDeHumano(Exception):
    """Erro na fase crítica (já a meio de algo irreversível).

    Distingue-se de um erro transitório: não se faz retry, pára-se e chama-se
    o humano com o browser aberto no ponto onde parou.
    """


# --------------------------------------------------------------------------
# Log
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def perguntar(texto: str, default: str = "") -> str:
    """Pergunta ao utilizador na consola. Nada fica guardado em disco."""
    sufixo = f" [{default}]" if default else ""
    resposta = input(f"{texto}{sufixo}: ").strip()
    return resposta or default


# --------------------------------------------------------------------------
# Browser
# --------------------------------------------------------------------------

def abrir_browser(playwright, perfil_dir: str, headless: bool = False,
                  slow_mo: int = 0):
    """Abre um Chromium com perfil persistente.

    O perfil guarda cookies e sessão entre execuções: o utilizador faz login à
    mão uma vez e as execuções seguintes já entram autenticadas. Evita ter de
    automatizar logins (que parte com 2FA e captcha) e evita guardar
    credenciais em disco.

    ATENÇÃO: a pasta do perfil contém a sessão iniciada do utilizador.
    Acrescenta-a ao .gitignore e nunca a partilhes.
    """
    os.makedirs(perfil_dir, exist_ok=True)
    contexto = playwright.chromium.launch_persistent_context(
        user_data_dir=os.path.abspath(perfil_dir),
        headless=headless,
        slow_mo=slow_mo,
        viewport={"width": 1440, "height": 900},
    )
    page = contexto.pages[0] if contexto.pages else contexto.new_page()
    return contexto, page


def confirmar_login(page: Page, url_inicial: str,
                    instrucao: str = "Confirma que tens sessão iniciada") -> None:
    """Abre o site e espera que o humano confirme que está autenticado."""
    ir_para(page, url_inicial)
    aceitar_cookies(page)
    print()
    print(f">>> Na janela do browser: {instrucao}.")
    print(">>> Se não tiveres, faz login agora nessa janela.")
    input(">>> Quando estiveres pronto, prime Enter: ")


def sessao_expirou(page: Page,
                   padrao: str = r"login|signin|sign-in|autentica") -> bool:
    """True se a URL atual parece uma página de login.

    Chama isto antes de assumir que estás autenticado. Sessão expirada a meio
    de um fluxo é sempre PrecisaDeHumano, nunca um retry.
    """
    return bool(re.search(padrao, page.url, re.I))


# --------------------------------------------------------------------------
# Navegação
# --------------------------------------------------------------------------

def ir_para(page: Page, url: str, esperado: str = "", tentativas: int = 4,
            espera_s: float = 2.0) -> None:
    """Navega para `url` tolerando redirects do próprio site.

    Um redirect durante o carregamento interrompe o goto() e levanta exceção
    mesmo quando a navegação acabou por correr bem. Por isso confirmamos o
    destino pela URL final e não pelo facto de o goto não ter rebentado.

    `esperado`: fragmento que a URL final deve conter. Se vazio, usa-se o path
    do url pedido.
    """
    ultimo_erro: Optional[Exception] = None
    for _ in range(tentativas):
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            ultimo_erro = e
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
        alvo = esperado or url.split("//", 1)[-1].split("/", 1)[-1]
        if alvo in page.url or page.url.rstrip("/") == url.rstrip("/"):
            return
        time.sleep(espera_s)
    if ultimo_erro:
        log(f"Aviso: navegação instável para {url} (fiquei em {page.url})")


# --------------------------------------------------------------------------
# Banners de cookies
# --------------------------------------------------------------------------

_SELETORES_COOKIES = (
    "#onetrust-reject-all-handler",
    "#onetrust-accept-btn-handler",
    "button#didomi-notice-agree-button",
    "button[aria-label*='Aceitar' i]",
    "button[aria-label*='Accept' i]",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
)

_CONTENTORES_COOKIES = (
    "#onetrust-consent-sdk",
    "#didomi-host",
    "#CybotCookiebotDialog",
    "[id*='cookie-banner' i]",
    "[class*='cookie-consent' i]",
)


def aceitar_cookies(page: Page, timeout_ms: int = 6000) -> None:
    """Fecha o banner de cookies, com cascata de fallbacks.

    Banners tapam elementos e fazem cliques falhar com erros que não fazem
    sentido ("element intercepts pointer events"). Preferimos rejeitar quando
    há essa opção; se nada funcionar, removemos o nó por JavaScript, que
    resolve o problema prático de ele estar por cima do conteúdo.
    """
    for seletor in _SELETORES_COOKIES:
        try:
            botao = page.locator(seletor).first
            botao.wait_for(state="visible", timeout=timeout_ms // len(_SELETORES_COOKIES) or 1000)
            botao.click()
            time.sleep(0.5)
            return
        except Exception:
            continue

    for seletor in ("Rejeitar", "Recusar", "Aceitar", "Accept all", "Reject all"):
        try:
            botao = page.get_by_role("button", name=re.compile(seletor, re.I)).first
            if botao.is_visible():
                botao.click()
                time.sleep(0.5)
                return
        except Exception:
            continue

    remover_overlays(page)


def remover_overlays(page: Page) -> None:
    """Remove por JavaScript os contentores de consentimento que sobrarem."""
    for seletor in _CONTENTORES_COOKIES:
        try:
            page.evaluate(
                "s => document.querySelectorAll(s).forEach(e => e.remove())", seletor)
        except Exception:
            continue


# --------------------------------------------------------------------------
# Preencher campos
# --------------------------------------------------------------------------

def escrever_e_confirmar(campo: Locator, valor: str, delay: int = 50,
                         descricao: str = "") -> None:
    """Escreve num campo e verifica que o valor ficou lá.

    `fill()` define o valor por baixo do capô e campos com JavaScript reativo
    (React, Vue, autocompletes) muitas vezes não reparam — o site continua a
    achar que o campo está vazio e o botão seguinte fica desativado sem
    explicação. `type()` simula teclas reais e dispara os eventos; o Tab no fim
    dispara a validação; a verificação transforma uma falha silenciosa numa
    falha que diz o que aconteceu.
    """
    nome = descricao or "campo"
    campo.wait_for(state="visible", timeout=15000)
    campo.click()
    campo.fill("")
    campo.type(valor, delay=delay)
    campo.press("Tab")
    atual = (campo.input_value() or "").strip()
    if atual != valor.strip():
        raise PrecisaDeHumano(
            f"O {nome} não registou o valor (escrevi '{valor}', ficou '{atual}').")


def escolher_autocomplete(page: Page, campo: Locator, valor: str,
                          timeout_ms: int = 8000) -> None:
    """Escreve num autocomplete e escolhe a sugestão correspondente.

    Autocompletes precisam de dois tempos: escrever, esperar pela lista, e
    clicar. Clicar antes de a lista aparecer apanha o item errado ou nenhum.
    """
    campo.wait_for(state="visible", timeout=15000)
    campo.click()
    campo.fill("")
    campo.type(valor, delay=70)

    sugestao = page.locator("li, [role='option'], .autocomplete-item").filter(
        has_text=re.compile(re.escape(valor), re.I))
    try:
        sugestao.first.wait_for(state="visible", timeout=timeout_ms)
        sugestao.first.click()
    except Exception:
        # fallback: navegar a lista pelo teclado
        campo.press("ArrowDown")
        campo.press("Enter")


def escolher_dropdown(page: Page, opcao: str, texto_atual: str = "") -> None:
    """Escolhe uma opção num dropdown, seja `<select>` nativo ou combobox custom.

    Tenta primeiro os selects nativos (rápido e fiável). Se nenhum aceitar a
    opção, assume um combobox feito com divs: clica no texto atual para abrir
    e depois na opção.
    """
    for select in page.locator("select").all():
        try:
            select.select_option(label=opcao)
            return
        except Exception:
            continue

    if texto_atual:
        page.get_by_text(texto_atual, exact=True).first.click()
    page.get_by_text(opcao, exact=True).first.click(timeout=10000)


def carregar_ficheiro(page: Page, valor_ficheiro: str,
                      rotulo: str = "CV|Resume|Curriculum|file") -> None:
    """Faz upload de um ficheiro.

    `set_input_files` no `<input type=file>` funciona mesmo quando o input está
    escondido atrás de um botão bonito — é preferível a clicar no botão e
    apanhar o diálogo do sistema operativo, que o Playwright não controla.
    """
    if not os.path.exists(valor_ficheiro):
        raise PrecisaDeHumano(f"Ficheiro não existe: {valor_ficheiro}")
    entrada = page.locator("input[type='file']").first
    entrada.wait_for(state="attached", timeout=15000)
    entrada.set_input_files(valor_ficheiro)


# --------------------------------------------------------------------------
# Cliques
# --------------------------------------------------------------------------

def clicar_quando_ativo(locator: Locator, descricao: str,
                        timeout_ms: int = 25000) -> None:
    """Espera que o elemento fique ATIVO (não apenas visível) e clica.

    Visível não é o mesmo que clicável. Um botão desativado está lá e o click()
    do Playwright espera por ele até rebentar com um timeout genérico. Na
    prática, botão desativado quase sempre significa "há um campo obrigatório
    por preencher" — por isso o erro diz isso, em vez de TimeoutError.
    """
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
        f"de um campo obrigatório que não foi preenchido.")


def marcar_checkbox(page: Page, locator: Optional[Locator] = None) -> None:
    """Marca uma checkbox, incluindo as 'custom' tapadas por um span.

    Sites com checkboxes estilizadas escondem o input real e desenham um span
    por cima. O check() normal não lhe chega; o force ignora a interceção, e se
    ainda assim não marcar, clica-se no span visível.
    """
    checkbox = locator or page.get_by_role("checkbox").first
    checkbox.wait_for(state="attached", timeout=10000)
    try:
        checkbox.check(force=True)
    except Exception:
        pass
    if checkbox.is_checked():
        return
    for seletor in ("span.custom-checkbox", "label", ".checkmark"):
        try:
            page.locator(seletor).first.click()
            if checkbox.is_checked():
                return
        except Exception:
            continue
    raise PrecisaDeHumano("Não consegui marcar a checkbox.")


# --------------------------------------------------------------------------
# Diagnóstico
# --------------------------------------------------------------------------

def guardar_diagnostico(page: Page, nome: str = "erro",
                        pasta: str = "diagnostico") -> str:
    """Guarda screenshot + HTML do estado atual.

    Quando algo falha, o que resolve o problema é ver o que o browser via. O
    HTML serve para procurar o seletor que faltou; o screenshot para perceber
    se havia um modal por cima. Os nomes têm timestamp para não se
    sobreporem entre tentativas.

    Cuidado: se a página tiver dados sensíveis, estes ficheiros também ficam.
    """
    os.makedirs(pasta, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(pasta, f"{nome}_{carimbo}")
    try:
        page.screenshot(path=f"{base}.png", full_page=True)
    except Exception:
        pass
    try:
        with open(f"{base}.html", "w", encoding="utf-8") as fh:
            fh.write(page.content())
    except Exception:
        pass
    log(f"Diagnóstico guardado em {base}.png / .html (URL: {page.url})")
    return base


# --------------------------------------------------------------------------
# Alertas e energia (multi-plataforma)
# --------------------------------------------------------------------------

def alertar(mensagem: str, titulo: str = "Automação") -> None:
    """Alerta impossível de ignorar quando o utilizador não está a olhar.

    Um print não chega: se o script corre durante horas, a pessoa foi fazer
    outra coisa. Som + notificação do sistema, com fallback para a consola.
    """
    log(f"*** {titulo}: {mensagem}")
    sistema = platform.system()
    try:
        if sistema == "Windows":
            import winsound
            import ctypes
            for _ in range(3):
                winsound.Beep(1500, 400)
                winsound.Beep(1000, 400)
            ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, 0x40 | 0x1000)
        elif sistema == "Darwin":
            os.system(f'osascript -e \'display notification "{mensagem}" '
                      f'with title "{titulo}" sound name "Glass"\'')
        else:
            os.system(f'notify-send "{titulo}" "{mensagem}" 2>/dev/null')
            sys.stdout.write("\a" * 3)
            sys.stdout.flush()
    except Exception:
        print("\n" + "!" * 60)
        print(f"{titulo}: {mensagem}")
        print("!" * 60 + "\n")


class manter_pc_acordado:
    """Context manager que impede a máquina de suspender durante a execução.

    Um monitor que corre horas é inútil se o PC adormece a meio. Repõe sempre
    as definições à saída, mesmo com exceção — daí ser context manager e não
    duas funções soltas.

    Uso:
        with manter_pc_acordado():
            ...
    """

    def __init__(self) -> None:
        self._processo = None

    def __enter__(self):
        sistema = platform.system()
        try:
            if sistema == "Windows":
                import ctypes
                ES_CONTINUOUS = 0x80000000
                ES_SYSTEM_REQUIRED = 0x00000001
                ctypes.windll.kernel32.SetThreadExecutionState(
                    ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                log("O PC não vai suspender enquanto isto correr.")
            elif sistema == "Darwin":
                import subprocess
                self._processo = subprocess.Popen(["caffeinate", "-dimsu"])
                log("O Mac não vai suspender enquanto isto correr.")
        except Exception as e:
            log(f"Não consegui impedir a suspensão ({e}). Continuo na mesma.")
        return self

    def __exit__(self, *exc):
        try:
            if platform.system() == "Windows":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            elif self._processo is not None:
                self._processo.terminate()
            log("Definições de suspensão repostas.")
        except Exception:
            pass
        return False


# --------------------------------------------------------------------------
# Ciclo de vigia com política de erro em duas fases
# --------------------------------------------------------------------------

def vigiar(page: Page, verificar, agir, intervalo_s: int = 30,
           max_tentativas: Optional[int] = None) -> bool:
    """Vigia uma página até uma condição acontecer, depois age.

    A distinção que faz este ciclo valer a pena: erros ANTES da condição são
    transitórios (o site abanou, a rede caiu) e retomam-se em silêncio; erros
    DEPOIS, já a meio de algo irreversível, param tudo, fazem barulho, e deixam
    o browser no ponto onde parou para o humano acabar à mão. Tentar recuperar
    sozinho a meio de uma transação é como se perdem compras e candidaturas.

    `verificar(page) -> bool`  — a condição aconteceu?
    `agir(page)`               — a fase crítica; pode levantar PrecisaDeHumano.

    Devolve True se `agir` correu até ao fim sem erro.
    """
    tentativa = 0
    while max_tentativas is None or tentativa < max_tentativas:
        tentativa += 1
        try:
            if verificar(page):
                log(f"Condição encontrada (tentativa {tentativa}). Fase crítica.")
                try:
                    agir(page)
                    alertar("Concluído com sucesso.", "Automação")
                    return True
                except Exception as e:
                    guardar_diagnostico(page, "fase_critica")
                    alertar(
                        f"PRECISO DE TI: {e}\n\nO browser está aberto no passo "
                        f"onde parou. Acaba à mão AGORA.", "Automação — ação necessária")
                    input("Prime Enter quando terminares...")
                    return False
            log(f"Tentativa {tentativa}: sem novidade. Nova em {intervalo_s}s.")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log(f"Tentativa {tentativa}: erro transitório "
                f"({type(e).__name__}: {e}). Continuo.")
            guardar_diagnostico(page, "vigia")
        time.sleep(intervalo_s)
    log(f"Limite de {max_tentativas} tentativas atingido sem sucesso.")
    return False
