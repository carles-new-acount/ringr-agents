# Registro de decisiones

Notas tomadas durante el desarrollo. Al final se resumen en el README.

## Parte 1: estructura y modelos simulados

**Layout `src/` + `pyproject.toml`.** Evita que los tests importen el código
por accidente desde la raíz del repo: obligan a instalar el paquete
(`pip install -e .`), igual que lo usaría un consumidor real.

**Sin dependencias en runtime.** Las integraciones HTTP son simuladas, así que no
hace falta `requests` ni `httpx`. Solo `pytest` como dependencia de desarrollo.

**Los modelos reciben la conversación.** El enunciado define qué devuelven
`answer_user` y `parse_data`, pero no qué reciben. Un LLM real necesitaría el
historial, así que ambos reciben un objeto `Conversation`. Los simulados lo
ignoran, pero la firma ya es la que tendría la versión real: sustituirlos no
obliga a tocar los agentes.

**Modelos "guionizados".** El enunciado dice que los modelos genéricos tienen
en su estado interno todo lo necesario y que no hacen falta subclases por caso
de uso. Por eso cada modelo recibe una lista de salidas, una por turno. Así los
tests son deterministas y cada escenario se describe en pocas líneas.

**Fallar de forma explícita.** Si se pide un turno más de los guionizados se
lanza `ScriptExhaustedError` con un mensaje claro, en lugar de repetir la última
salida o devolver `None`. Un mock que falla en silencio esconde errores en los
tests.

**`parse_data` devuelve una copia.** El agente va a normalizar los datos; si
modificara el dict original estaría cambiando el guion del test.

**Supuesto: el parser devuelve el estado acumulado.** En cada turno,
`parse_data` devuelve lo extraído de *toda* la conversación, no solo del último
mensaje. Es lo natural en un LLM que recibe el historial completo y simplifica
el agente: no tiene que ir fusionando datos parciales de cada turno.

**Herencia en los modelos simulados.** `_ScriptedModel` es privada y solo existe
para no duplicar la lógica de "siguiente salida". `ConversationModel` y
`ParserModel` siguen siendo las dos clases que pide el enunciado.
