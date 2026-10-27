# 📄 Asistente de Postulaciones con IA

Aplicación personal que adapta tu CV y redacta el correo de postulación para cada
oferta laboral, usando IA (GPT-4o). Pensada originalmente para búsqueda de empleo
en el área legal, pero funciona para cualquier profesión.

## ¿Qué hace?

1. **Ingresas una oferta** laboral (pegando el texto o subiendo una imagen/captura).
2. La IA **lee tu CV maestro** (toda tu experiencia real) y genera un CV adaptado
   específicamente a esa oferta — priorizando lo relevante, conectando competencias
   transferibles, y redactando en forma impersonal/profesional — además de un
   borrador de correo de postulación.
   Si lo activas, antes de redactar la IA **investiga la empresa u organismo** en internet
   (a qué se dedica, noticias recientes, qué suele valorar) y adapta el CV y el correo con eso.
   Todo lo que la IA cree plausible pero tu CV maestro no afirma te lo **pregunta** (pestaña
   «Por confirmar»): solo entra al CV lo que tú confirmes.
3. **Revisas y editas** el borrador: todos los campos a la vez y un solo botón para aplicar.
4. **Descargas el CV en PDF**, con diseño prolijo tipo "Harvard resume", listo para
   enviar junto al correo.
5. Cada corrección que haces queda **guardada como aprendizaje**: la próxima vez,
   la IA intenta escribir más parecido a como tú corriges.
6. Cada postulación generada queda en tu **historial**, con estado editable
   (Generada / Enviada / Respondida / Entrevista / Rechazada).

## Requisitos

- Python 3.10+
- Una cuenta y API key de OpenAI (con saldo/billing activo)

## Instalación

```powershell
# 1. Crear y activar entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate         # Mac/Linux

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar tu API key
# Crea un archivo .env en la raíz del proyecto con:
#   OPENAI_API_KEY=tu_key_aqui

# 4. Agregar las tipografías (no vienen incluidas por tamaño)
# Descarga Poppins-Regular.ttf y Poppins-Bold.ttf (Google Fonts, licencia OFL)
# y colócalas en una carpeta fonts/ en la raíz del proyecto.

# 5. Ejecutar
streamlit run app.py
```

La primera vez que la abras, como no existe `cv_maestro.txt`, la app te va a pedir
pegar tu CV completo y (opcionalmente) tu LinkedIn directamente en la pantalla de
bienvenida — no hace falta crear ningún archivo a mano.

## Estructura del proyecto

```
postulaciones-ia/
├── app.py                     # La app (UI + lógica + generación de PDF)
├── buscar_ofertas.py          # Búsqueda diaria automática de ofertas (corre aparte de la app)
├── buscar_ofertas.bat         # Lanzador para el Programador de Tareas de Windows
├── requirements.txt           # Dependencias
├── test_app.py                # Pruebas de la app
├── test_buscar_ofertas.py     # Pruebas de la búsqueda automática
├── test_interfaz.py           # Pruebas que recorren la app como una persona (IA simulada)
├── .env                       # Tus claves: OPENAI_API_KEY y APIFY_API_TOKEN (no se sube a git)
├── fonts/
│   ├── Poppins-Regular.ttf
│   └── Poppins-Bold.ttf
├── cv_maestro.txt             # Tu CV completo (se crea desde la app)
├── config.json                # Tu LinkedIn y otras preferencias (se crea desde la app)
├── postulaciones.json         # Historial de postulaciones (incluye las "Sugeridas")
├── historial_ediciones.json   # Correcciones guardadas para "entrenar" el estilo
├── ofertas_vistas.json        # Ofertas ya revisadas por la búsqueda automática
├── investigaciones_empresas.json  # Caché de empresas investigadas (30 días)
└── buscar_ofertas.log         # Registro de cada ejecución de la búsqueda automática
```

Los archivos .json, .env y .log son datos tuyos, generados en tu primer uso — agrégalos a
`.gitignore` si en algún momento subes este proyecto a un repositorio.

## Investigación de la empresa y sugerencias por confirmar

En el paso 1 puedes escribir la empresa, organismo o lugar que ofrece el cargo (si lo dejas
vacío, la IA lo busca en el texto de la oferta). Con «Investigar la organización» activado:

1. La IA consulta la web (herramienta `web_search` de la API de Responses de OpenAI) y arma
   un resumen: a qué se dedica, noticias recientes, qué suele valorar y fuentes con enlaces.
2. Ese contexto se usa para ajustar el énfasis del CV y el correo (con a lo más un dato
   concreto de la empresa en el correo, y solo si la confianza es alta o media).
3. Si algo sería valioso para la oferta pero tu CV maestro no lo afirma, aparece en la pestaña
   **Por confirmar** como pregunta (ej. «¿Has gestionado trámites notariales?»). Eliges
   «Sí, lo he hecho → incluir», «No → descartar» o «Decidir después». Lo que no marques no se agrega.

Cuidados: la información viene de internet y la reúne una IA, así que puede equivocarse (la
tarjeta muestra la confianza y las fuentes: verifícala antes de citarla en una entrevista). Cada
búsqueda tiene un costo pequeño; la misma empresa no se vuelve a consultar por 30 días. Si la
búsqueda falla, el CV se genera igual, solo con la oferta.

## Búsqueda automática de ofertas

`buscar_ofertas.py` corre una vez al día (sin abrir la app) y hace esto:

1. Consulta el actor de Apify [`crawler_cl/job-scraper-chile`](https://apify.com/crawler_cl/job-scraper-chile)
   con tus palabras clave (varios portales chilenos en una sola ejecución).
2. Descarta gratis lo repetido, antiguo o que no parece jurídico.
3. Puntúa el calce de cada oferta con tu CV maestro (modelo barato, gpt-4o-mini).
4. Para las que superan el umbral (60/100 por defecto) prepara el CV y el correo y las deja
   en **Mis postulaciones** con estado **Sugerida**, con su puntaje, la razón y el link a la oferta.

**Nunca envía nada**: tú revisas las sugerencias desde la app. Al abrir una sugerida,
editarla y generar el PDF, pasa a "Generada".

Configuración (palabras clave, ciudad, fuentes, umbral, topes de gasto): constantes al
inicio de `buscar_ofertas.py`.

```powershell
python buscar_ofertas.py --demo     # prueba con ofertas de ejemplo: sin Apify y sin guardar nada
python buscar_ofertas.py            # ejecución real (requiere APIFY_API_TOKEN en .env)
```

Para que corra solo cada día (ajusta la hora):

```powershell
schtasks /Create /SC DAILY /ST 08:00 /TN BuscarOfertasAbogado /TR C:\Users\TU_USUARIO\postulaciones-ia\buscar_ofertas.bat
```

El computador debe estar encendido a esa hora (en el Programador de Tareas puedes activar
"ejecutar la tarea lo antes posible si se perdió el inicio programado"). Si algo falla, el
detalle queda en `buscar_ofertas.log`.

**Costos:** Apify cobra por ejecución más uso de plataforma; el script limita el gasto por
búsqueda (`MAX_COSTO_USD_POR_BUSQUEDA`) y la IA por día. Tras la primera corrida real,
revisa el costo en Apify Console > Billing y ajusta los topes.

## Cómo funciona el aprendizaje de estilo

Cada vez que editas un borrador generado y confirmas, la app compara campo por
campo lo que propuso la IA vs. lo que dejaste tú. Si hay diferencias, las guarda
como ejemplo ("así no" / "así sí"). En la próxima postulación, le muestra a la IA
tus últimas 3 correcciones como referencia de estilo. No es un reentrenamiento
real del modelo, sino aprendizaje por ejemplos dentro del prompt — pero en la
práctica ayuda a que la redacción converja hacia tu forma de escribir.

## Límites conocidos

- La IA nunca inventa experiencia que no esté en tu CV maestro — si falta algo,
  agrégalo ahí primero.
- Un solo usuario por instalación (no es una app multiusuario/web pública).
- La búsqueda automática depende de un actor de Apify mantenido por la comunidad: puede
  fallar o cambiar sin aviso, y los portales pueden bloquear o modificar sus páginas.

## Stack técnico

Python · Streamlit · Apify · OpenAI API (GPT-4o, con visión para leer imágenes) · ReportLab
(generación de PDF) · Tipografía Poppins
