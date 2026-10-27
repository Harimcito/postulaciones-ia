"""
Pruebas automatizadas para app.py.

Cómo correrlas:
    pip install pytest
    pytest test_app.py -v

Nota técnica: app.py es un script de Streamlit (se ejecuta de arriba a abajo,
no es un módulo diseñado para importarse). Por eso estas pruebas "simulan"
streamlit con un mock mínimo y ejecutan solo la parte de app.py anterior al
flujo de pantallas (donde están todas las funciones reutilizables), tal como
se hizo manualmente durante el desarrollo de esta app.
"""
import os
import sys
import json
import types
import contextlib
import tempfile

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Carga las funciones de app.py en un entorno aislado y temporal,
    para que cada prueba parta de cero y no toque tus archivos reales."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key-para-tests")

    # .env mínimo para que python-dotenv no reviente buscando hacia arriba
    (tmp_path / ".env").write_text("OPENAI_API_KEY=dummy-key-para-tests")

    # Fuentes falsas: no probamos el PDF real de reportlab con Poppins aquí,
    # pero la función de registro de fuentes necesita encontrar los archivos.
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    _crear_ttf_minimo(fonts_dir / "Poppins-Regular.ttf")
    _crear_ttf_minimo(fonts_dir / "Poppins-Bold.ttf")

    st_mock = types.ModuleType("streamlit")
    for fn in ["set_page_config", "title", "markdown", "caption", "divider",
               "metric", "error", "warning", "info", "success", "write"]:
        setattr(st_mock, fn, lambda *a, **k: None)
    st_mock.sidebar = contextlib.nullcontext()
    st_mock.expander = lambda *a, **k: contextlib.nullcontext()
    st_mock.button = lambda *a, **k: False

    class EstadoSesion(dict):
        def __getattr__(self, k):
            return self[k]

        def __setattr__(self, k, v):
            self[k] = v

    st_mock.session_state = EstadoSesion()
    monkeypatch.setitem(sys.modules, "streamlit", st_mock)

    app_path = os.path.join(os.path.dirname(__file__), "app.py")
    codigo = open(app_path, encoding="utf-8").read()
    # Nos quedamos solo con las funciones reutilizables, antes de que empiece
    # el flujo de pantallas (ETAPA 1 en adelante, que asume una sesión real).
    codigo_backend = codigo.split(
        "# ============================================================\n# ETAPA 1"
    )[0]

    # __file__ apunta a la carpeta temporal (no a la real) para que
    # cv_maestro.txt, postulaciones.json, etc. se lean/escriban ahí y cada
    # prueba quede completamente aislada de las demás y de tus datos reales.
    espacio = {"__file__": str(tmp_path / "app.py")}
    exec(codigo_backend, espacio)
    return espacio


def _crear_ttf_minimo(path):
    """Crea un archivo que reportlab pueda registrar como fuente TTF real,
    copiando una fuente del sistema si existe; si no, el test de fuentes se salta solo."""
    import glob
    candidatos = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    if candidatos:
        import shutil
        shutil.copy(candidatos[0], path)
    else:
        path.write_bytes(b"")  # dejará que falle el registro; no es crítico para estas pruebas


# ---------------------------------------------------------------------------
# escapar(): nunca debe dejar pasar caracteres que rompan el PDF
# ---------------------------------------------------------------------------

def test_escapar_caracteres_especiales(app):
    escapar = app["escapar"]
    assert escapar("Contratos & Cía") == "Contratos &amp; Cía"
    assert escapar("Experiencia <societaria>") == "Experiencia &lt;societaria&gt;"
    assert escapar("") == ""
    assert escapar(None) == ""


# ---------------------------------------------------------------------------
# Historial de postulaciones: crear, actualizar sin duplicar, cambiar estado
# ---------------------------------------------------------------------------

def _cv_prueba(**overrides):
    base = {
        "nombre": "Harim Amade Valenzuela", "titulo": "Abogado", "contacto": "Santiago, Chile",
        "resumen": "Resumen de prueba", "experiencia": "Cargo — Empresa | Santiago | 2024\n- Logro",
        "educacion": "Título — Universidad (2021)", "habilidades": "Derecho corporativo",
        "idiomas": "Español", "correo_asunto": "Postulación", "correo_cuerpo": "Estimados...",
        "empresa_oferta": "Estudio XYZ", "cargo_oferta": "Abogado Senior",
    }
    base.update(overrides)
    return base


def test_guardar_postulacion_nueva(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    cargar = app["cargar_postulaciones"]

    pid = guardar(_cv_prueba(), None)
    todas = cargar()

    assert len(todas) == 1
    assert todas[0]["id"] == pid
    assert todas[0]["estado"] == "Generada"
    assert todas[0]["empresa_oferta"] == "Estudio XYZ"


def test_actualizar_postulacion_no_duplica(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    cargar = app["cargar_postulaciones"]

    pid = guardar(_cv_prueba(), None)
    guardar(_cv_prueba(resumen="Resumen editado"), pid)

    todas = cargar()
    assert len(todas) == 1  # no se duplicó
    assert todas[0]["cv"]["resumen"] == "Resumen editado"


def test_cambiar_estado_postulacion(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    actualizar_estado = app["actualizar_estado_postulacion"]
    cargar = app["cargar_postulaciones"]

    pid = guardar(_cv_prueba(), None)
    actualizar_estado(pid, "Enviada")

    assert cargar()[0]["estado"] == "Enviada"


# ---------------------------------------------------------------------------
# Detección de duplicados
# ---------------------------------------------------------------------------

def test_detecta_postulacion_duplicada(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    buscar_similar = app["buscar_postulacion_similar"]

    guardar(_cv_prueba(), None)

    assert buscar_similar("Estudio XYZ", "Abogado Senior") is not None
    assert buscar_similar("  estudio xyz ", "ABOGADO senior") is not None  # insensible a formato


def test_no_marca_falso_positivo(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    buscar_similar = app["buscar_postulacion_similar"]

    guardar(_cv_prueba(), None)

    assert buscar_similar("Otra Empresa", "Otro Cargo") is None


def test_duplicado_se_excluye_a_si_mismo(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    buscar_similar = app["buscar_postulacion_similar"]

    pid = guardar(_cv_prueba(), None)

    assert buscar_similar("Estudio XYZ", "Abogado Senior", excluir_id=pid) is None


# ---------------------------------------------------------------------------
# Aprendizaje de correcciones (historial_ediciones.json)
# ---------------------------------------------------------------------------

def test_guardar_correcciones_solo_si_hay_cambios(app):
    guardar_correcciones = app["guardar_correcciones"]
    cargar_historial = app["cargar_historial"]

    original = _cv_prueba()
    # Sin cambios reales: no debe guardar nada
    guardar_correcciones(original, dict(original))
    assert cargar_historial() == []

    # Con un cambio real en un campo de aprendizaje: sí debe guardarlo
    editado = dict(original, resumen="Un resumen distinto y mejor redactado")
    guardar_correcciones(original, editado)
    historial = cargar_historial()
    assert len(historial) == 1
    assert "resumen" in historial[0]["cambios"]


# ---------------------------------------------------------------------------
# Generación de PDF: no debe reventar con texto normal ni con símbolos raros
# ---------------------------------------------------------------------------

def test_generar_pdf_no_revienta_con_texto_normal(app):
    generar_pdf = app["generar_pdf"]
    pdf_bytes = generar_pdf(_cv_prueba())
    assert pdf_bytes.startswith(b"%PDF")


def test_generar_pdf_no_revienta_con_caracteres_especiales(app):
    generar_pdf = app["generar_pdf"]
    cv = _cv_prueba(
        nombre="Harim <Amade> & Valenzuela",
        resumen="Experiencia en M&A y due diligence <societario> > $1.000.000 UF.",
        habilidades="M&A, derecho < societario >",
    )
    pdf_bytes = generar_pdf(cv)
    assert pdf_bytes.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# Postulaciones "Sugeridas" por la búsqueda automática
# ---------------------------------------------------------------------------

def test_guardar_postulacion_sugerida_con_origen(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    cargar = app["cargar_postulaciones"]

    guardar(_cv_prueba(), None, estado="Sugerida",
            extra={"origen": {"portal": "laborum", "puntaje": 82, "url": "https://x.cl/1"}})

    p = cargar()[0]
    assert p["estado"] == "Sugerida"
    assert p["origen"]["puntaje"] == 82


def test_editar_una_sugerida_la_pasa_a_generada_y_conserva_el_origen(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    cargar = app["cargar_postulaciones"]

    pid = guardar(_cv_prueba(), None, estado="Sugerida", extra={"origen": {"puntaje": 70}})
    guardar(_cv_prueba(resumen="Editado por el usuario"), pid)  # el usuario la revisó y generó el PDF

    p = cargar()[0]
    assert p["estado"] == "Generada"
    assert p["origen"]["puntaje"] == 70
    assert len(cargar()) == 1


def test_actualizar_no_pisa_un_estado_avanzado(app):
    guardar = app["guardar_o_actualizar_postulacion"]
    actualizar_estado = app["actualizar_estado_postulacion"]
    cargar = app["cargar_postulaciones"]

    pid = guardar(_cv_prueba(), None)
    actualizar_estado(pid, "Enviada")
    guardar(_cv_prueba(resumen="Retoque"), pid)

    assert cargar()[0]["estado"] == "Enviada"


# ---------------------------------------------------------------------------
# Sugerencias por confirmar
# ---------------------------------------------------------------------------

def test_normalizar_sugerencias_limpia_invalidas_y_limita(app):
    normalizar = app["normalizar_sugerencias"]
    validas = {"seccion": "habilidades", "texto": "Trámites notariales", "pregunta": "¿Los has hecho?"}
    crudas = [validas, {"seccion": "otra", "texto": "x"}, {"seccion": "resumen", "texto": ""},
              "basura", None, dict(validas)]  # inválidas + una duplicada
    resultado = normalizar(crudas)

    assert len(resultado) == 1 and resultado[0]["seccion"] == "habilidades"
    assert normalizar([validas])[0]["id"] == resultado[0]["id"]  # el id es estable
    assert normalizar("no es una lista") == []
    muchas = [{"seccion": "habilidades", "texto": f"t{i}"} for i in range(12)]
    assert len(normalizar(muchas)) == app["MAX_SUGERENCIAS"]


def test_aplicar_sugerencia_en_habilidades_resumen_y_educacion(app):
    aplicar = app["aplicar_sugerencia"]
    cv = {"habilidades": "Contratos, Compliance,", "resumen": "Abogado corporativo", "educacion": "Licenciado — UAI (2021)"}

    assert aplicar(cv, {"seccion": "habilidades", "texto": "Trámites notariales"})
    assert cv["habilidades"] == "Contratos, Compliance, Trámites notariales"

    assert aplicar(cv, {"seccion": "resumen", "texto": "Con foco en regulación CMF."})
    assert cv["resumen"] == "Abogado corporativo. Con foco en regulación CMF."

    assert aplicar(cv, {"seccion": "educacion", "texto": "Diplomado en Compliance — PUC (2026)"})
    assert cv["educacion"].endswith("\nDiplomado en Compliance — PUC (2026)")


def test_aplicar_sugerencia_no_duplica_si_se_aplica_dos_veces(app):
    aplicar = app["aplicar_sugerencia"]
    cv = {"habilidades": "Contratos"}
    sug = {"seccion": "habilidades", "texto": "Compliance"}
    aplicar(cv, sug)
    aplicar(cv, sug)
    assert cv["habilidades"] == "Contratos, Compliance"


def test_aplicar_sugerencia_en_experiencia_ubica_el_bloque_correcto(app):
    aplicar = app["aplicar_sugerencia"]
    cv = {"experiencia": "Abogado Senior — Estudio A | Santiago | 2025\n- Logro A1\n\n"
                         "Abogado Junior — Estudio B | Santiago | 2023\n- Logro B1"}

    assert aplicar(cv, {"seccion": "experiencia", "bloque": "Abogado Junior — Estudio B", "texto": "- Apoyo en due diligence."})
    bloque_a, bloque_b = cv["experiencia"].split("\n\n")
    assert "due diligence" not in bloque_a           # no se coló en el bloque equivocado
    assert bloque_b.endswith("\n- Apoyo en due diligence.")  # y no quedó con guion doble

    antes = cv["experiencia"]
    assert not aplicar(cv, {"seccion": "experiencia", "bloque": "Cargo inexistente — Otra Empresa", "texto": "x"})
    assert not aplicar(cv, {"seccion": "experiencia", "bloque": "", "texto": "x"})
    assert not aplicar(cv, {"seccion": "inventada", "texto": "x"})
    assert cv["experiencia"] == antes


def test_md_seguro_neutraliza_formato_e_imagenes(app):
    seguro = app["_md_seguro"]("![x](http://malo.cl/p.png) **fuerte** <b>html</b>")
    assert "![" not in seguro and "**" not in seguro.replace("\\*", "") and "<b>" not in seguro.replace("\\<", "")
    assert app["_md_seguro"](None) == ""


# ---------------------------------------------------------------------------
# Investigación de la empresa (búsqueda web simulada)
# ---------------------------------------------------------------------------

import types as _types


class _FalsoResponses:
    def __init__(self, salida, falla_tipos=(), anotaciones=None):
        self.salida, self.falla_tipos = salida, set(falla_tipos)
        self.anotaciones = anotaciones or []
        self.llamadas = []

    def create(self, **kw):
        self.llamadas.append(kw)
        if kw["tools"][0]["type"] in self.falla_tipos:
            raise RuntimeError("herramienta no soportada")
        return _types.SimpleNamespace(
            output_text=self.salida,
            output=[_types.SimpleNamespace(content=[_types.SimpleNamespace(annotations=self.anotaciones)])])


class _FalsoChat:
    def __init__(self, contenido="{}", error=None):
        self.contenido, self.error, self.prompts = contenido, error, []
        self.completions = self

    def create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        if self.error:
            raise self.error
        mensaje = _types.SimpleNamespace(content=self.contenido)
        return _types.SimpleNamespace(choices=[_types.SimpleNamespace(message=mensaje)])


def _cliente(responses=None, chat=None):
    return _types.SimpleNamespace(responses=responses, chat=chat or _FalsoChat())


def _anot(url, titulo="Fuente"):
    return _types.SimpleNamespace(type="url_citation", url=url, title=titulo)


JSON_INVESTIGACION = """Aquí tienes el resultado:
```json
{"empresa_identificada": "Banco Demo S.A.", "confianza": "ALTA",
 "resumen": "Banco comercial con foco en pymes.", "datos_clave": ["Sede en Santiago"],
 "noticias_recientes": [
   {"titulo": "Noticia 1", "fecha": "2026-09", "detalle": "d1"}, {"titulo": "Noticia 2", "fecha": "", "detalle": "d2"},
   {"titulo": "Noticia 3", "fecha": "2026-05", "detalle": "d3"}, {"titulo": "Noticia 4", "fecha": "2026-01", "detalle": "d4"}],
 "que_valoran": ["Cumplimiento normativo"], "implicancias_cv": ["Resaltar compliance"], "advertencias": []}
```"""


def test_investigar_empresa_parsea_normaliza_y_cita_fuentes(app):
    falso = _FalsoResponses(JSON_INVESTIGACION, anotaciones=[
        _anot("https://banco-demo.cl/nosotros", "Sitio oficial"),
        _anot("javascript:alert(1)", "malicioso"),       # esquema peligroso: se descarta
        _anot("https://banco-demo.cl/nosotros", "repetida"),
    ])
    app["client"] = _cliente(responses=falso)

    inv = app["investigar_empresa"]("Banco Demo", "oferta de abogado")

    assert inv["empresa_identificada"] == "Banco Demo S.A."
    assert inv["confianza"] == "alta"                    # se normaliza a minúscula
    assert len(inv["noticias_recientes"]) == 3           # tope de 3
    assert [f["url"] for f in inv["fuentes"]] == ["https://banco-demo.cl/nosotros"]
    assert falso.llamadas[0]["tools"] == [{"type": "web_search"}]
    assert falso.llamadas[0]["model"] == app["MODELO_INVESTIGACION"]
    assert "Banco Demo" in falso.llamadas[0]["input"]


def test_investigar_empresa_usa_cache_y_no_vuelve_a_cobrar(app):
    falso = _FalsoResponses(JSON_INVESTIGACION)
    app["client"] = _cliente(responses=falso)

    app["investigar_empresa"]("Banco Demo", "oferta")
    segunda = app["investigar_empresa"]("  banco   DEMO ", "otra oferta")   # mismo nombre, otro formato

    assert len(falso.llamadas) == 1 and segunda["desde_cache"] is True
    app["investigar_empresa"]("Banco Demo", "oferta", usar_cache=False)
    assert len(falso.llamadas) == 2


def test_cache_de_investigacion_vence(app):
    from datetime import datetime, timedelta
    vieja = (datetime.now() - timedelta(days=app["DIAS_VIGENCIA_INVESTIGACION"] + 1)).strftime("%Y-%m-%d")
    app["guardar_investigacion_cache"]("Banco Demo", {"resumen": "x", "consultada": vieja})
    assert app["buscar_investigacion_cache"]("Banco Demo") is None


def test_investigar_empresa_cae_a_la_herramienta_anterior(app):
    falso = _FalsoResponses(JSON_INVESTIGACION, falla_tipos=("web_search",))
    app["client"] = _cliente(responses=falso)

    inv = app["investigar_empresa"]("Banco Demo")

    assert inv is not None
    assert [c["tools"][0]["type"] for c in falso.llamadas] == ["web_search", "web_search_preview"]


@pytest.mark.parametrize("salida, falla_tipos", [
    ("no es json", ()),                                   # respuesta sin JSON
    ('{"resumen": "", "confianza": "alta"}', ()),         # sin contenido útil
    (JSON_INVESTIGACION, ("web_search", "web_search_preview")),  # la API falla con ambas herramientas
])
def test_investigar_empresa_devuelve_none_si_no_hay_informacion_util(app, salida, falla_tipos):
    app["client"] = _cliente(responses=_FalsoResponses(salida, falla_tipos=falla_tipos))
    assert app["investigar_empresa"]("Banco Demo") is None
    assert app["investigar_empresa"]("") is None


def test_identificar_empresa(app):
    app["client"] = _cliente(chat=_FalsoChat('{"empresa": "Banco Demo"}'))
    assert app["identificar_empresa"]("Oferta de abogado en Banco Demo") == "Banco Demo"

    app["client"] = _cliente(chat=_FalsoChat('{"empresa": "No identificada"}'))
    assert app["identificar_empresa"]("texto") == ""

    app["client"] = _cliente(chat=_FalsoChat(error=RuntimeError("caída")))
    assert app["identificar_empresa"]("texto") == ""


def test_generar_borrador_usa_la_investigacion_y_normaliza_sugerencias(app):
    respuesta = {k: "x" for k in app["CAMPOS_BORRADOR"]}
    respuesta["sugerencias"] = [
        {"seccion": "habilidades", "texto": "Trámites notariales", "pregunta": "¿Los has hecho?", "respaldo": "ninguno"},
        {"seccion": "inventada", "texto": "descartar"},
    ]
    chat = _FalsoChat(json.dumps(respuesta))
    app["client"] = _cliente(chat=chat)
    investigacion = {"nombre_consultado": "Banco Demo", "confianza": "alta",
                     "resumen": "Banco comercial con foco en pymes.", "noticias_recientes": []}

    borrador = app["generar_borrador"]("CV maestro", "Oferta", investigacion)

    assert "INVESTIGACIÓN SOBRE LA ORGANIZACIÓN" in chat.prompts[0]
    assert "Banco comercial con foco en pymes." in chat.prompts[0]
    assert len(borrador["sugerencias"]) == 1 and borrador["sugerencias"][0]["id"]

    app["generar_borrador"]("CV maestro", "Oferta")  # sin investigación: ese bloque no aparece
    assert "INVESTIGACIÓN SOBRE LA ORGANIZACIÓN" not in chat.prompts[1]


def test_mostrar_investigacion_no_revienta_con_datos_completos(app):
    inv = {"nombre_consultado": "Banco Demo", "empresa_identificada": "Banco Demo S.A.", "confianza": "media",
           "resumen": "Resumen (con paréntesis) y *marcas*", "datos_clave": ["a"], "consultada": "2026-10-01",
           "noticias_recientes": [{"titulo": "T", "fecha": "", "detalle": "d"}], "que_valoran": ["v"],
           "implicancias_cv": ["i"], "advertencias": ["ojo"], "desde_cache": True,
           "fuentes": [{"titulo": "Sitio (oficial)", "url": "https://x.cl/a_(b)"}, {"titulo": "mala", "url": "javascript:x"}]}
    app["mostrar_investigacion"](inv)
    app["mostrar_investigacion"]({})  # incluso con un dict vacío
