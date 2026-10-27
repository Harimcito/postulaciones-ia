"""
Pruebas de buscar_ofertas.py (no usan internet, ni Apify, ni OpenAI: todo está simulado).

    pytest test_buscar_ofertas.py -v
"""
import importlib.util
import json
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buscar_ofertas.py")
spec = importlib.util.spec_from_file_location("buscar_ofertas", RUTA)
bo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bo)

LOGGER = logging.getLogger("test_buscar_ofertas")


def oferta(**kw):
    base = {"id": "1", "source": "laborum", "url": "https://x.cl/1", "title": "Abogado Corporativo",
            "company_name": "Estudio A", "description": "Derecho societario.", "location": "Santiago",
            "posted_date": datetime.now().strftime("%Y-%m-%d")}
    base.update(kw)
    return base


# ----------------------------- filtros gratuitos -----------------------------

def test_juridica_por_titulo_con_tildes_y_mayusculas():
    assert bo.es_oferta_juridica({"title": "ASESOR JURÍDICO", "description": ""})
    assert bo.es_oferta_juridica({"title": "Analista de Compliance", "description": ""})


def test_juridica_por_descripcion_exige_dos_terminos_distintos():
    assert not bo.es_oferta_juridica({"title": "Ejecutivo", "description": "Conocimiento legal básico."})
    assert bo.es_oferta_juridica({"title": "Ejecutivo", "description": "Apoyo legal en temas tributarios."})


def test_no_juridica():
    assert not bo.es_oferta_juridica({"title": "Desarrollador Python", "description": "Django y AWS"})
    assert not bo.es_oferta_juridica({})


def test_es_reciente():
    hoy = datetime(2026, 10, 20)
    assert bo.es_reciente({"posted_date": "2026-10-10"}, dias_max=21, hoy=hoy)
    assert not bo.es_reciente({"posted_date": "2026-08-01"}, dias_max=21, hoy=hoy)
    assert bo.es_reciente({}, hoy=hoy)                              # sin fecha: se asume reciente
    assert bo.es_reciente({"posted_date": "hace 3 días"}, hoy=hoy)  # formato raro: se asume reciente


def test_claves_detectan_misma_oferta_en_distintos_portales():
    a = oferta(source="linkedin", id="L1", title="Abogado Corporativo", company_name="Estudio  A")
    b = oferta(source="indeed", id="I9", title="abogado corporativo", company_name="estudio a")
    assert set(bo.claves_oferta(a)) & set(bo.claves_oferta(b))


def test_construir_texto_incluye_datos_y_recorta():
    texto = bo.construir_texto_oferta(oferta(description="x" * 10000), max_chars=500)
    assert len(texto) <= 500
    assert "Cargo: Abogado Corporativo" in texto and "Empresa: Estudio A" in texto


# ------------------------- memoria de ofertas vistas -------------------------

def test_vistas_se_guardan_y_se_recuperan(tmp_path):
    ruta = str(tmp_path / "vistas.json")
    vistas = {}
    o = oferta()
    assert not bo.ya_vista(o, vistas)
    bo.marcar_vista(o, vistas, "sugerida")
    bo.guardar_vistas(vistas, ruta)
    recuperadas = bo.cargar_vistas(ruta)
    assert bo.ya_vista(o, recuperadas)


def test_vistas_antiguas_se_olvidan(tmp_path):
    ruta = tmp_path / "vistas.json"
    vieja = (datetime.now() - timedelta(days=bo.DIAS_RETENCION_VISTAS + 5)).isoformat(timespec="seconds")
    ruta.write_text(json.dumps({"id:laborum:1": {"fecha": vieja, "resultado": "x"}}))
    assert bo.cargar_vistas(str(ruta)) == {}


def test_vistas_archivo_corrupto_no_revienta(tmp_path):
    ruta = tmp_path / "vistas.json"
    ruta.write_text("{esto no es json")
    assert bo.cargar_vistas(str(ruta)) == {}


# ----------------------- orquestación completa (simulada) -----------------------

class Entorno:
    """Dependencias falsas que registran qué se llamó."""

    def __init__(self, puntajes=None, historial=None, falla_generar=False):
        self.puntajes = puntajes or {}
        self.historial = historial or set()
        self.falla_generar = falla_generar
        self.evaluadas, self.generadas, self.guardadas = [], [], []

    def evaluar(self, cv, texto):
        self.evaluadas.append(texto)
        for titulo, puntaje in self.puntajes.items():
            if titulo in texto:
                return {"puntaje": puntaje, "razon": f"razon {puntaje}"}
        return {"puntaje": 10, "razon": "sin datos"}

    def generar(self, cv, texto):
        self.generadas.append(texto)
        return None if self.falla_generar else {"resumen": "resumen", "empresa_oferta": "E", "cargo_oferta": "C"}

    def guardar(self, cv, estado, extra):
        self.guardadas.append((cv, estado, extra))
        return "id"

    def similar(self, empresa, cargo):
        return {"id": "previo"} if (empresa, cargo) in self.historial else None


def correr(ofertas, env, vistas=None, **kw):
    return bo.procesar_ofertas(
        ofertas, "CV", evaluar=env.evaluar, generar=env.generar, guardar=env.guardar,
        similar=env.similar, vistas={} if vistas is None else vistas, logger=LOGGER, **kw)


def test_flujo_completo_aprueba_descarta_y_filtra():
    ofertas = [
        oferta(id="1", title="Abogado Corporativo Semi Senior", company_name="Estudio A"),
        oferta(id="2", title="Abogado Tributario Junior", company_name="Estudio B"),
        oferta(id="3", title="Desarrollador Python", company_name="Tech", description="Django"),
        oferta(id="4", title="Abogado Antiguo", company_name="Estudio C", posted_date="2020-01-01"),
        oferta(id="1", title="Abogado Corporativo Semi Senior", company_name="Estudio A"),  # repetida
    ]
    env = Entorno(puntajes={"Semi Senior": 85, "Tributario Junior": 30})
    vistas = {}
    stats = correr(ofertas, env, vistas)

    assert stats["recibidas"] == 5
    assert stats["repetidas"] == 1
    assert stats["no_juridicas"] == 1
    assert stats["antiguas"] == 1
    assert stats["evaluadas"] == 2           # la IA solo vio las 2 jurídicas y recientes
    assert stats["bajo_umbral"] == 1
    assert stats["sugeridas"] == 1
    assert len(env.guardadas) == 1
    cv, estado, extra = env.guardadas[0]
    assert estado == "Sugerida"
    assert extra["origen"]["puntaje"] == 85 and extra["origen"]["portal"] == "laborum"
    assert extra["origen"]["url"] == "https://x.cl/1"


def test_segunda_ejecucion_no_repite_trabajo_ni_costo():
    ofertas = [oferta(id="1", title="Abogado Corporativo A", company_name="Estudio A")]
    vistas = {}
    env1 = Entorno(puntajes={"Corporativo A": 90})
    correr(ofertas, env1, vistas)
    env2 = Entorno(puntajes={"Corporativo A": 90})
    stats2 = correr(ofertas, env2, vistas)
    assert stats2["repetidas"] == 1
    assert env2.evaluadas == [] and env2.generadas == [] and env2.guardadas == []


def test_no_sugiere_si_ya_esta_en_el_historial():
    ofertas = [oferta(id="1", title="Abogado Corporativo", company_name="Estudio A")]
    env = Entorno(puntajes={"Corporativo": 90}, historial={("Estudio A", "Abogado Corporativo")})
    stats = correr(ofertas, env)
    assert stats["ya_en_historial"] == 1 and stats["sugeridas"] == 0
    assert env.generadas == [] and env.guardadas == []


def test_respeta_tope_de_borradores_y_prioriza_mejor_puntaje():
    ofertas = [oferta(id=str(i), title=f"Abogado {i}", company_name=f"Estudio {i}") for i in range(5)]
    env = Entorno(puntajes={"Abogado 0": 70, "Abogado 1": 95, "Abogado 2": 80, "Abogado 3": 65, "Abogado 4": 90})
    vistas = {}
    stats = correr(ofertas, env, vistas, max_borradores=2)
    assert stats["sugeridas"] == 2
    assert [g[2]["origen"]["puntaje"] for g in env.guardadas] == [95, 90]
    assert stats["pendientes"] == 3
    # las no procesadas por el tope NO quedan marcadas: mañana se reintentan
    assert not bo.ya_vista(ofertas[0], vistas)


def test_respeta_tope_de_evaluaciones():
    ofertas = [oferta(id=str(i), title=f"Abogado {i}", company_name=f"E{i}") for i in range(10)]
    env = Entorno()
    stats = correr(ofertas, env, max_evaluaciones=4)
    assert len(env.evaluadas) == 4 and stats["pendientes"] >= 6


def test_si_la_ia_falla_no_se_marca_como_vista_para_reintentar():
    ofertas = [oferta(id="1", title="Abogado Corporativo", company_name="Estudio A")]
    vistas = {}
    stats = bo.procesar_ofertas(
        ofertas, "CV", evaluar=lambda cv, t: None, generar=lambda cv, t: None, guardar=lambda *a: "id",
        similar=lambda e, c: None, vistas=vistas, logger=LOGGER)
    assert stats["errores"] == 1 and vistas == {}


def test_si_falla_la_generacion_no_guarda_ni_marca():
    ofertas = [oferta(id="1", title="Abogado Corporativo", company_name="Estudio A")]
    env = Entorno(puntajes={"Corporativo": 90}, falla_generar=True)
    vistas = {}
    stats = correr(ofertas, env, vistas)
    assert stats["errores"] == 1 and stats["sugeridas"] == 0
    assert env.guardadas == [] and not bo.ya_vista(ofertas[0], vistas)


def test_modo_prueba_no_guarda_nada():
    ofertas = [oferta(id="1", title="Abogado Corporativo", company_name="Estudio A")]
    env = Entorno(puntajes={"Corporativo": 90})
    stats = bo.procesar_ofertas(
        ofertas, "CV", evaluar=env.evaluar, generar=env.generar, guardar=None,
        similar=env.similar, vistas={}, logger=LOGGER)
    assert stats["sugeridas"] == 1 and env.guardadas == []


def test_persiste_memoria_durante_el_proceso():
    ofertas = [oferta(id="1", title="Abogado Corporativo", company_name="Estudio A")]
    llamadas = []
    env = Entorno(puntajes={"Corporativo": 20})
    correr(ofertas, env, persistir=lambda v: llamadas.append(dict(v)))
    assert llamadas, "debería haber guardado la memoria al descartar la oferta"


# ------------------------------ evaluar_calce ------------------------------

class FalsoOpenAI:
    def __init__(self, contenido=None, error=None):
        self.chat = self
        self.completions = self
        self._contenido, self._error = contenido, error

    def create(self, **kwargs):
        if self._error:
            raise self._error
        mensaje = type("M", (), {"content": self._contenido})()
        return type("R", (), {"choices": [type("C", (), {"message": mensaje})()]})()


def test_evaluar_calce_normal_y_limita_el_rango():
    r = bo.evaluar_calce(FalsoOpenAI('{"puntaje": 130, "razon": "ok"}'), "CV", "oferta")
    assert r == {"puntaje": 100, "razon": "ok"}
    r = bo.evaluar_calce(FalsoOpenAI('{"puntaje": -5, "razon": "mal"}'), "CV", "oferta")
    assert r["puntaje"] == 0


def test_evaluar_calce_devuelve_none_si_la_ia_falla():
    assert bo.evaluar_calce(FalsoOpenAI(error=RuntimeError("caída")), "CV", "oferta") is None
    assert bo.evaluar_calce(FalsoOpenAI("esto no es json"), "CV", "oferta") is None
    assert bo.evaluar_calce(FalsoOpenAI('["no", "es", "objeto"]'), "CV", "oferta") is None


# -------------------------------- Apify (falso) --------------------------------

class FalsoRun:
    def __init__(self, dataset_id="ds1", status="SUCCEEDED"):
        self.default_dataset_id, self.status, self.usage_total_usd = dataset_id, status, 0.01


class FalsoApify:
    def __init__(self, items_por_keyword, fallan=()):
        self.items_por_keyword, self.fallan = items_por_keyword, set(fallan)
        self.llamadas = []
        self._keyword_actual = None

    def actor(self, actor_id):
        self.actor_id = actor_id
        return self

    def call(self, **kwargs):
        keyword = kwargs["run_input"]["keyword"]
        self.llamadas.append(kwargs)
        if keyword in self.fallan:
            raise RuntimeError("actor caído")
        self._keyword_actual = keyword
        return FalsoRun(dataset_id=f"ds-{keyword}")

    def dataset(self, dataset_id):
        self._ds = dataset_id
        return self

    def iterate_items(self):
        return iter(self.items_por_keyword[self._ds.replace("ds-", "")])


def test_apify_junta_resultados_y_pasa_los_parametros_correctos():
    falso = FalsoApify({"abogado": [{"id": "1"}, {"id": "2"}], "tributario": [{"id": "3"}]})
    res = bo.buscar_en_apify("tok", ["abogado", "tributario"], "Chile", "Santiago", ["laborum"], 25,
                             LOGGER, max_costo_usd=0.4, cliente=falso)
    assert [r["id"] for r in res] == ["1", "2", "3"]
    entrada = falso.llamadas[0]["run_input"]
    assert entrada["keyword"] == "abogado" and entrada["mode"] == "portals"
    assert entrada["sources"] == ["laborum"] and entrada["max_results"] == 25
    assert entrada["country"] == "Chile" and entrada["city"] == "Santiago"
    assert falso.llamadas[0]["max_total_charge_usd"] == Decimal("0.4")  # tope de gasto activo
    assert falso.actor_id == "crawler_cl/job-scraper-chile"


def test_apify_si_una_busqueda_falla_sigue_con_las_demas():
    falso = FalsoApify({"abogado": [{"id": "1"}], "tributario": [{"id": "3"}]}, fallan=["abogado"])
    res = bo.buscar_en_apify("tok", ["abogado", "tributario"], "Chile", "Santiago", ["laborum"], 25,
                             LOGGER, cliente=falso)
    assert [r["id"] for r in res] == ["3"]


# ------------------------- integración con app.py real -------------------------

def test_cargar_backend_expone_las_funciones_que_el_script_necesita(tmp_path, monkeypatch):
    """Verifica que app.py sigue siendo compatible con buscar_ofertas.py (si alguien renombra
    una función o el marcador '# ETAPA 1' en app.py, esta prueba avisa)."""
    app_real = os.path.join(os.path.dirname(RUTA), "app.py")
    if not os.path.exists(app_real):
        pytest.skip("app.py no está en la misma carpeta")

    (tmp_path / "fonts").mkdir()
    import glob
    import shutil
    ttfs = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    if not ttfs:
        pytest.skip("no hay fuentes TTF del sistema para simular Poppins")
    shutil.copy(ttfs[0], tmp_path / "fonts" / "Poppins-Regular.ttf")
    shutil.copy(ttfs[0], tmp_path / "fonts" / "Poppins-Bold.ttf")
    (tmp_path / "cv_maestro.txt").write_text("CV de prueba", encoding="utf-8")
    (tmp_path / "app.py").write_text(open(app_real, encoding="utf-8").read(), encoding="utf-8")

    monkeypatch.setattr(bo, "APP_PATH", str(tmp_path / "app.py"))
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=dummy")
    monkeypatch.chdir(tmp_path)

    import sys
    streamlit_antes = sys.modules.get("streamlit")
    ns = bo.cargar_backend(LOGGER)
    assert sys.modules.get("streamlit") is streamlit_antes, "cargar_backend dejó un Streamlit falso instalado"
    for nombre in ["generar_borrador", "guardar_o_actualizar_postulacion",
                   "buscar_postulacion_similar", "cv_maestro", "client"]:
        assert nombre in ns, f"app.py ya no expone '{nombre}'"
    assert ns["cv_maestro"] == "CV de prueba"

    # y guardar con estado "Sugerida" + origen funciona de punta a punta
    pid = ns["guardar_o_actualizar_postulacion"](
        {"nombre": "N", "empresa_oferta": "E", "cargo_oferta": "C"}, None,
        estado="Sugerida", extra={"origen": {"puntaje": 77}})
    guardada = [p for p in ns["cargar_postulaciones"]() if p["id"] == pid][0]
    assert guardada["estado"] == "Sugerida" and guardada["origen"]["puntaje"] == 77
