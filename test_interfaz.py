"""
Pruebas de la interfaz (recorren la app completa como lo haría una persona).

Usan el simulador de Streamlit (AppTest) y un OpenAI falso: no gastan API ni usan internet.

    pytest test_interfaz.py -v
"""
import glob
import json
import os
import shutil
import types

import pytest
from streamlit.testing.v1 import AppTest

AQUI = os.path.dirname(os.path.abspath(__file__))
OFERTA = "Banco Demo busca abogado/a corporativo con experiencia en contratos y cumplimiento normativo."


# ----------------------------- OpenAI falso -----------------------------

class FalsoOpenAI:
    """Reemplaza a openai.OpenAI. La configuración y el registro viven en la clase porque
    la app crea un cliente nuevo en cada ejecución del script."""
    registro: list = []
    busqueda_falla: bool = False
    herramientas_que_fallan: set = set()
    sugerencias: list = []

    def __init__(self, *a, **k):
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._chat))
        self.responses = types.SimpleNamespace(create=self._responses)

    @classmethod
    def reiniciar(cls):
        cls.registro, cls.busqueda_falla, cls.herramientas_que_fallan = [], False, set()
        cls.sugerencias = [
            {"seccion": "habilidades", "bloque": "", "texto": "Trámites notariales",
             "pregunta": "¿Has gestionado trámites notariales?", "respaldo": "modificaciones societarias"},
            {"seccion": "experiencia", "bloque": "Abogado Corporativo — Estudio A", "texto": "Apoyo en due diligence.",
             "pregunta": "¿Participaste en due diligence?", "respaldo": "ninguno"},
        ]

    def _chat(self, **kw):
        prompt = kw["messages"][0]["content"]
        self.registro.append(("chat", kw["model"], prompt))
        if "extrae el nombre de la empresa" in prompt:
            contenido = {"empresa": "Banco Demo"}
        else:
            contenido = {
                "nombre": "Harim Amade", "titulo": "Abogado", "contacto": "Santiago | x@y.cl",
                "resumen": "Abogado con experiencia corporativa.",
                "experiencia": "Abogado Corporativo — Estudio A | Santiago | 2024\n- Redacción de contratos.",
                "educacion": "Licenciado — UAI (2021)", "habilidades": "Contratos", "idiomas": "Español",
                "correo_asunto": "Postulación", "correo_cuerpo": "Estimados...",
                "empresa_oferta": "Banco Demo", "cargo_oferta": "Abogado Corporativo",
                "sugerencias": self.sugerencias,
            }
        mensaje = types.SimpleNamespace(content=json.dumps(contenido))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=mensaje)])

    def _responses(self, **kw):
        tipo = kw["tools"][0]["type"]
        self.registro.append(("responses", tipo, kw["input"]))
        if self.busqueda_falla or tipo in self.herramientas_que_fallan:
            raise RuntimeError("búsqueda no disponible")
        salida = json.dumps({
            "empresa_identificada": "Banco Demo S.A.", "confianza": "alta",
            "resumen": "Banco comercial con foco en pymes.", "datos_clave": ["Sede en Santiago"],
            "noticias_recientes": [{"titulo": "Abrió nueva sucursal", "fecha": "2026-09", "detalle": "Expansión regional"}],
            "que_valoran": ["Cumplimiento normativo"], "implicancias_cv": ["Resaltar compliance"], "advertencias": []})
        cita = types.SimpleNamespace(type="url_citation", url="https://banco-demo.cl/nosotros", title="Sitio oficial")
        return types.SimpleNamespace(
            output_text=salida, output=[types.SimpleNamespace(content=[types.SimpleNamespace(annotations=[cita])])])

    # utilidades de las pruebas
    @classmethod
    def llamadas(cls, tipo):
        return [r for r in cls.registro if r[0] == tipo]

    @classmethod
    def prompt_de_generacion(cls):
        return [r[2] for r in cls.llamadas("chat") if "asistente experto en reclutamiento" in r[2]][-1]


# ------------------------------- entorno -------------------------------

@pytest.fixture()
def proyecto(tmp_path, monkeypatch):
    """Copia de la app en una carpeta temporal: así sus archivos de datos (historial,
    caché, etc.) nunca tocan los tuyos."""
    shutil.copy(os.path.join(AQUI, "app.py"), tmp_path / "app.py")
    fuentes = tmp_path / "fonts"
    fuentes.mkdir()
    origen = os.path.join(AQUI, "fonts")
    if os.path.exists(os.path.join(origen, "Poppins-Regular.ttf")):
        shutil.copy(os.path.join(origen, "Poppins-Regular.ttf"), fuentes)
        shutil.copy(os.path.join(origen, "Poppins-Bold.ttf"), fuentes)
    else:
        ttfs = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
        if not ttfs:
            pytest.skip("no hay fuentes para generar el PDF")
        shutil.copy(ttfs[0], fuentes / "Poppins-Regular.ttf")
        shutil.copy(ttfs[0], fuentes / "Poppins-Bold.ttf")
    (tmp_path / "cv_maestro.txt").write_text("CV maestro de prueba: abogado con experiencia corporativa.", encoding="utf-8")

    FalsoOpenAI.reiniciar()
    monkeypatch.setattr("openai.OpenAI", FalsoOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    return tmp_path


def abrir(proyecto):
    at = AppTest.from_file(str(proyecto / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def por_etiqueta(elementos, etiqueta):
    return [e for e in elementos if e.label == etiqueta][0]


def boton(at, inicio):
    return [b for b in at.button if b.label.startswith(inicio)][0]


def generar(at, oferta=OFERTA, empresa="", investigar=True):
    por_etiqueta(at.text_area, "Texto de la oferta").set_value(oferta)
    if empresa:
        por_etiqueta(at.text_input, "Empresa, organismo o lugar que ofrece el cargo (opcional)").set_value(empresa)
    at.toggle[0].set_value(investigar)
    boton(at, "✨").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


# ----------------------- generación con investigación -----------------------

def test_flujo_con_investigacion_muestra_tarjeta_y_sugerencias(proyecto):
    at = generar(abrir(proyecto))

    assert at.session_state["etapa"] == "borrador"
    assert any("Lo que la IA averiguó sobre Banco Demo S.A." in e.label for e in at.expander)
    assert [t.label for t in at.tabs][-1] == "💡 Por confirmar (2)"

    investigacion = at.session_state["cv_borrador"]["investigacion"]
    assert investigacion["resumen"] == "Banco comercial con foco en pymes."
    assert investigacion["fuentes"][0]["url"] == "https://banco-demo.cl/nosotros"

    # la búsqueda web se usó con la herramienta actual, y el CV se generó CON esa información
    assert FalsoOpenAI.llamadas("responses")[0][1] == "web_search"
    prompt = FalsoOpenAI.prompt_de_generacion()
    assert "INVESTIGACIÓN SOBRE LA ORGANIZACIÓN" in prompt and "Banco comercial con foco en pymes." in prompt


def test_sin_investigar_no_hay_busqueda_ni_tarjeta(proyecto):
    at = generar(abrir(proyecto), investigar=False)

    assert FalsoOpenAI.llamadas("responses") == []
    assert "investigacion" not in at.session_state["cv_borrador"]
    assert not any("averiguó" in e.label for e in at.expander)
    assert "INVESTIGACIÓN SOBRE LA ORGANIZACIÓN" not in FalsoOpenAI.prompt_de_generacion()


def test_si_la_busqueda_falla_el_cv_se_genera_igual_y_avisa(proyecto):
    FalsoOpenAI.busqueda_falla = True
    at = generar(abrir(proyecto))

    assert at.session_state["etapa"] == "borrador"          # no se bloquea el flujo principal
    assert "investigacion" not in at.session_state["cv_borrador"]
    assert any("No se pudo investigar a «Banco Demo»" in i.value for i in at.info)


def test_si_web_search_no_existe_usa_web_search_preview(proyecto):
    FalsoOpenAI.herramientas_que_fallan = {"web_search"}
    at = generar(abrir(proyecto))

    assert [r[1] for r in FalsoOpenAI.llamadas("responses")] == ["web_search", "web_search_preview"]
    assert at.session_state["cv_borrador"]["investigacion"]["confianza"] == "alta"


def test_la_empresa_escrita_a_mano_manda_y_evita_identificarla(proyecto):
    at = generar(abrir(proyecto), empresa="Corte de Apelaciones de Arica")

    assert at.session_state["cv_borrador"]["empresa_oferta"] == "Corte de Apelaciones de Arica"
    assert not any("extrae el nombre de la empresa" in r[2] for r in FalsoOpenAI.llamadas("chat"))
    assert "Corte de Apelaciones de Arica" in FalsoOpenAI.llamadas("responses")[0][2]


def test_la_misma_empresa_no_se_vuelve_a_investigar(proyecto):
    generar(abrir(proyecto))
    assert len(FalsoOpenAI.llamadas("responses")) == 1

    at2 = abrir(proyecto)  # otra sesión, otra postulación a la misma empresa
    generar(at2)
    assert len(FalsoOpenAI.llamadas("responses")) == 1      # salió del caché: no se cobró otra búsqueda
    assert at2.session_state["cv_borrador"]["investigacion"]["desde_cache"] is True


# --------------------------- edición en un solo paso ---------------------------

def test_editar_varios_campos_y_aplicar_con_un_solo_clic(proyecto):
    at = generar(abrir(proyecto))

    por_etiqueta(at.text_input, "Nombre completo").set_value("Harim A. Valenzuela")
    por_etiqueta(at.text_area, "Perfil profesional").set_value("RESUMEN EDITADO")
    por_etiqueta(at.text_area, "Competencias clave").set_value("Contratos, Compliance")
    por_etiqueta(at.text_area, "Cuerpo del correo").set_value("CORREO EDITADO")
    at.radio(key=f"sug_{at.session_state['cv_borrador']['sugerencias'][0]['id']}").set_value("Sí, lo he hecho → incluir")
    boton(at, "💾").click()
    at.run()

    cv = at.session_state["cv_borrador"]
    assert not at.exception
    assert cv["nombre"] == "Harim A. Valenzuela" and cv["resumen"] == "RESUMEN EDITADO"
    assert cv["correo_cuerpo"] == "CORREO EDITADO"
    assert cv["habilidades"] == "Contratos, Compliance, Trámites notariales"   # editado + sugerencia confirmada
    assert at.session_state["etapa"] == "borrador"                              # sigue editando
    assert any("1 sugerencia(s) incluida(s)" in s.value for s in at.success)
    assert [t.label for t in at.tabs][-1] == "💡 Por confirmar (1)"             # la otra sigue pendiente


def test_sugerencia_rechazada_se_descarta_y_pendiente_se_conserva(proyecto):
    at = generar(abrir(proyecto))
    sugerencias = at.session_state["cv_borrador"]["sugerencias"]
    at.radio(key=f"sug_{sugerencias[0]['id']}").set_value("No → descartar")
    # la segunda queda en "Decidir después"
    boton(at, "💾").click()
    at.run()

    restantes = at.session_state["cv_borrador"]["sugerencias"]
    assert [s["id"] for s in restantes] == [sugerencias[1]["id"]]
    assert "Trámites notariales" not in at.session_state["cv_borrador"]["habilidades"]


def test_sugerencia_que_no_se_puede_ubicar_no_avanza_y_avisa(proyecto):
    FalsoOpenAI.sugerencias = [{"seccion": "experiencia", "bloque": "Cargo Inexistente — Otra Empresa",
                                "texto": "Algo que no calza.", "pregunta": "¿Lo hiciste?", "respaldo": ""}]
    at = generar(abrir(proyecto))
    at.radio(key=f"sug_{at.session_state['cv_borrador']['sugerencias'][0]['id']}").set_value("Sí, lo he hecho → incluir")
    boton(at, "✅").click()
    at.run()

    assert at.session_state["etapa"] == "borrador"          # no genera un PDF al que le falte algo
    assert any("No pude ubicar automáticamente" in w.value for w in at.warning)
    assert len(at.session_state["cv_borrador"]["sugerencias"]) == 1


# ----------------------- confirmar, PDF e historial -----------------------

def test_confirmar_genera_el_pdf_y_guarda_todo_en_el_historial(proyecto):
    at = generar(abrir(proyecto))
    por_etiqueta(at.text_area, "Perfil profesional").set_value("RESUMEN FINAL")
    boton(at, "✅").click()
    at.run()

    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["etapa"] == "final"

    guardadas = json.loads((proyecto / "postulaciones.json").read_text(encoding="utf-8"))
    assert len(guardadas) == 1
    registro = guardadas[0]
    assert registro["empresa_oferta"] == "Banco Demo" and registro["estado"] == "Generada"
    assert registro["cv"]["resumen"] == "RESUMEN FINAL"
    assert registro["cv"]["investigacion"]["resumen"] == "Banco comercial con foco en pymes."  # reabrirla conserva el contexto
    assert len(registro["cv"]["sugerencias"]) == 2                                            # las pendientes también


def test_volver_a_editar_desde_el_historial_conserva_investigacion_y_sugerencias(proyecto):
    at = generar(abrir(proyecto))
    boton(at, "✅").click()
    at.run()

    at2 = abrir(proyecto)
    at2.session_state["etapa"] = "historial"
    at2.run()
    boton(at2, "✏️ Editar").click()
    at2.run()

    assert not at2.exception
    assert at2.session_state["etapa"] == "borrador"
    assert any("averiguó" in e.label for e in at2.expander)
    assert [t.label for t in at2.tabs][-1] == "💡 Por confirmar (2)"
