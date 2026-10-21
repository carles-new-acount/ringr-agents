# Registro de decisiones

Razonamiento detrás de cada parte del proyecto, en el orden en que se construyó.
El README tiene el resumen; aquí están el detalle y las alternativas descartadas.

---

## 1. Estructura del proyecto

**Layout `src/` + `pyproject.toml`.** Con `src/`, los tests no pueden importar el
paquete "por accidente" desde la raíz del repo: obligan a instalarlo
(`pip install -e .`), igual que lo usaría cualquier consumidor. Así se detectan
errores de empaquetado.

**Sin dependencias en runtime.** Las integraciones HTTP son simuladas, así que no
hacen falta `requests` ni `httpx`. Para desarrollo: `pytest` y `ruff` (lint y
formato en una sola herramienta).

**Un módulo por responsabilidad** (conversación, modelos, validación, acciones,
integraciones, HTTP, agentes, composición). El proyecto es pequeño, pero el
enunciado pide poder escalar a nuevos agentes, acciones e integraciones, y cada
uno de esos ejes tiene su propio módulo.

## 2. Conversación y modelos simulados

**Los modelos reciben la conversación.** El enunciado define qué devuelven
`answer_user` y `parse_data`, pero no qué reciben. Un LLM real necesitaría el
historial, así que ambos reciben un objeto `Conversation`. Los simulados lo
ignoran, pero la firma ya es la que tendría la versión real: sustituirlos no
obliga a tocar los agentes.

**`Protocol` para los modelos.** Los agentes no dependen de las clases
`ConversationModel` y `ParserModel` concretas, sino de los protocolos
`SupportsAnswerUser` y `SupportsParseData`. Es tipado estructural (duck typing
comprobable por mypy): un cliente real de LLM puede usarse sin heredar de nada.
Es la "D" de SOLID (inversión de dependencias).

**Modelos "guionizados".** El enunciado dice que los modelos genéricos tienen en
su estado interno todo lo necesario y que no hacen falta subclases por caso de
uso. Por eso cada modelo recibe una lista de salidas, una por turno. Los tests
son deterministas y cada escenario se describe en pocas líneas.

**Fallar de forma explícita.** Si se pide un turno más de los guionizados se lanza
`ScriptExhaustedError` con un mensaje claro, en lugar de repetir la última
salida o devolver `None`. Un mock que falla en silencio esconde errores en los tests.

**`parse_data` devuelve una copia.** Así nadie puede modificar el guion desde fuera.

**Supuesto: el parser devuelve el estado acumulado.** En cada turno, `parse_data`
devuelve lo extraído de *toda* la conversación, no solo del último mensaje. Es lo
natural en un LLM que recibe el historial completo y simplifica el agente: no
tiene que ir fusionando datos parciales. Este supuesto tiene una consecuencia
directa: una vez registrado un compromiso, el parser lo seguirá devolviendo en
todos los turnos siguientes. **Por eso la deduplicación es imprescindible**, no
un extra.

**`Conversation.id` (UUID).** Sirve para generar la `Idempotency-Key` (ver punto 6)
y, en un sistema real, para trazar logs por conversación.

## 3. Validación y normalización (`validation.py`)

Son funciones puras: reciben un valor y devuelven el valor normalizado o lanzan
`InvalidFieldError`. Al ser funciones sin estado se testean de forma aislada y se
reutilizan entre agentes (`parse_text` sirve para cualquier campo de texto).

**Fechas: `strptime("%Y-%m-%d")` y no `date.fromisoformat`.** Desde Python 3.11,
`fromisoformat` acepta también formatos como `20261105`, y el contrato dice
`yyyy-mm-dd`. También rechaza fechas imposibles (`2026-02-30`).

**Importes:**
- `int` se acepta y se convierte a `float`, porque en JSON `150` y `150.0` son
  el mismo número.
- `bool` se rechaza explícitamente. En Python `True` es un `int`, así que sin
  esa comprobación `True` pasaría como `1.0`.
- NaN, infinito, cero y negativos se rechazan.
- Se redondea a 2 decimales: es dinero.
- Strings como `"150"` o `"150,50"` se rechazan. El contrato dice `float` y
  aceptar strings obligaría a decidir formatos locales (`,` frente a `.`). Si el
  parser se equivoca de tipo, es mejor no actuar que registrar un importe erróneo.

**Texto:** se colapsan todos los espacios en blanco (incluidos `\r\n`) y un texto
vacío o solo de espacios cuenta como "sin solicitud". Esto evita registrar
solicitudes vacías, hace que `"Cambiar  tarifa"` y `"Cambiar tarifa"` sean la
misma solicitud a efectos de duplicados y elimina los saltos de línea antes de
que lleguen a un header.

**Dato inválido = dato ausente.** En `BaseAgent._read_field`, un valor ausente,
`None` o inválido devuelven todos `None`, y el inválido además deja un warning
en el log. Alternativa descartada: lanzar una excepción y cortar el turno. Eso
dejaría al usuario sin respuesta por un error del parser. El objetivo es que un
dato dudoso **nunca** dispare una acción, no detener la conversación.

**Regla de negocio: la fecha no puede ser pasada.** No lo pide el enunciado, pero
un compromiso de pago con fecha de ayer no tiene sentido. "Hoy" se inyecta
(`today: Callable[[], date]`) para que los tests no dependan de la fecha real:
sin eso, un test con `2026-11-05` empezaría a fallar el 6 de noviembre. Vive en
`DebtAgent` y no en `validation.py` porque es una regla de negocio del agente de
cobros, no una validación genérica de formato.

## 4. Acciones (`actions.py`)

**`Action` describe *qué* hacer, no *cómo*.** `PaymentCommitment` y
`AssistanceRequest` solo contienen datos ya validados y saben convertirse a
payload JSON (`to_payload`). No saben nada de HTTP. Mañana el mismo
`AssistanceRequest` podría ir a una cola o a un CRM.

**Dataclasses inmutables (`frozen=True`).** Tienen dos ventajas:
1. No pueden cambiar entre que se deciden y se envían.
2. Son comparables y hasheables por valor, así que la deduplicación es un simple
   `set` y no hace falta inventar una "clave de duplicado" aparte.

**Datos tipados dentro de la acción.** `PaymentCommitment.commitment_date` es un
`date`, no un `str`. Una vez validado, el dato se representa con el tipo
correcto. Solo se convierte a string al serializar (`to_payload`).

## 5. Capa HTTP (`http_client.py`)

**`HttpRequest` inmutable.** Es el valor que el enunciado pide "construir
correctamente" (URL, headers y body), así que es un objeto propio que se puede
inspeccionar en los tests. Los headers y el body se congelan con
`MappingProxyType`, así que nadie puede modificar la request después de
construirla. `body` devuelve los bytes reales serializados en JSON, como irían
por la red.

**`HttpClient` abstracto + `FakeHttpClient`.** El fake guarda las requests en
`sent_requests` en lugar de enviarlas y devuelve 200 OK, como permite el
enunciado. Se puede configurar con otro `status_code` o una `error` para
simular fallos. Es un *fake* (una implementación real pero simplificada), no un
mock con `patch`: los tests comprueban comportamiento, no llamadas internas.

**`HttpTransportError`.** Distingue "no se pudo entregar" (timeout, red) de "el
servidor respondió con error" (no 2xx). Un cliente real traduciría sus propias
excepciones (`httpx.TimeoutException`...) a esta, así el resto del código no
depende de la librería HTTP.

## 6. Integraciones (`integrations.py`)

**`Integration` abstracta con `execute(action) -> ActionResult`.** Es el punto de
extensión para "nuevas integraciones". `HttpIntegration` es una implementación;
en `tests/test_extensibility.py` hay otra (`InMemoryQueueIntegration`) que no
usa HTTP, y el agente funciona igual con ella.

**`execute` no lanza excepciones por fallos de entrega.** Devuelve
`ActionResult(success=False, ...)`. Un fallo de una API externa es un resultado
esperable, no un error de programación, y el agente debe poder seguir
respondiendo al usuario.

**Construcción de la request (`build_request`):**
- `Authorization: Bearer <token>`, a través de un `Authenticator`
  intercambiable (API key, OAuth...).
- `Content-Type` y `Accept: application/json`.
- `Idempotency-Key`: ver más abajo.
- Los datos parseados como headers con el mismo nombre, como pide el enunciado.
  Los `None` se omiten, porque un header `commitment_date: None` no tiene sentido.
- **Los headers fijos se aplican después de los de datos.** Así un campo del
  parser llamado `Authorization` nunca podría sobrescribir la autenticación.
- Body: el payload en JSON.

**Codificación de los valores de los headers (`to_header_value`).** Los headers
solo admiten ASCII imprimible, sin CR/LF. `request` es texto libre del usuario,
lo que da dos problemas:
1. "dirección" lleva caracteres no ASCII, que muchos clientes no pueden enviar.
2. Un salto de línea permitiría **inyectar headers** (`"x\r\nX-Admin: true"`).

La solución es hacer percent-encoding de todo lo que no sea ASCII imprimible,
incluido el propio `%`, para que la codificación sea reversible. El body
conserva el valor original. Los valores numéricos y las fechas no cambian.

**Riesgos de mandar datos en headers** (documentados en el README, no
"arreglados", porque el enunciado lo pide explícitamente):
- nginx descarta por defecto los headers con guion bajo (`commitment_date`).
- Hay un límite de tamaño de unos 8 KB.
- Duplicar los datos en headers y body es redundante.

Lo propondría como cambio al equipo de la API en lugar de desviarme del
enunciado por mi cuenta.

**`Idempotency-Key`.** Es un hash SHA-256 de (id de conversación + tipo de acción
+ payload), determinista. La deduplicación en memoria del agente no puede cubrir
este caso: la request llega al servidor, se procesa, pero la respuesta se pierde
(timeout). El agente lo ve como `FAILED` y reintenta en el turno siguiente. Con
la misma `Idempotency-Key`, el servidor puede reconocer el reintento y no
registrar dos veces. Es un patrón estándar (Stripe, por ejemplo).

**El token no aparece en `repr`.** Se usa `field(repr=False)` en `BearerTokenAuth`
y en `Settings`, así el token no acaba en un log ni en un traceback.

## 7. Agentes (`agents/`)

**Template Method.** `BaseAgent.handle_turn` es concreto y fija el orden: guardar
el mensaje del usuario → responder → parsear → decidir → deduplicar → ejecutar.
Las subclases solo implementan `build_action(parsed_data) -> Action | None`.

Así ningún agente nuevo puede olvidarse de deduplicar o ejecutar acciones antes
de validarlas. La lógica crítica (la garantía de "solo si se cumplen las
condiciones" y "sin duplicados" que pide el enunciado) está en un único sitio y
testeada una vez.

Alternativa considerada: un pipeline de "pasos" configurable (lista de
`Step` objects). Lo descarté porque hay un único flujo y añadiría indirección sin
beneficio actual (YAGNI). Si aparecieran agentes con flujos realmente distintos,
el cambio sería sencillo porque `handle_turn` ya está separado en pasos claros.

**Herencia frente a composición.** Se usa herencia en un único nivel y solo para
el ciclo de vida. Todo lo que varía de forma independiente se inyecta por
composición: el modelo de conversación, el parser, la integración, el cliente
HTTP y la autenticación. Así no aparecen jerarquías del tipo
`HttpDebtAgentWithRetry`.

**Una instancia de agente = una conversación.** El estado de deduplicación
(`_executed_actions`) vive en la instancia. Es lo más simple que cumple
"no se envían duplicados durante la conversación".

**Qué es un duplicado.** Hay dos interpretaciones posibles:
1. Como máximo una acción por conversación.
2. No repetir la *misma* acción con los *mismos* datos.

Elegí la 2:
- En `AssistanceAgent` el usuario puede tener dos solicitudes distintas en una
  llamada, y ambas deben registrarse.
- En `DebtAgent`, si el usuario corrige el importe ("mejor 200 en vez de 150"),
  es un compromiso distinto y conviene registrarlo.

Se compara *después* de normalizar, así que `150` y `150.0` cuentan como la
misma acción. Si negocio prefiriera la opción 1 para cobros, bastaría con
sobrescribir la comprobación en `DebtAgent`.

**Solo se marcan como ejecutadas las acciones con éxito.** Si la API falla, el
resultado es `FAILED` y la acción no entra en `_executed_actions`. Si el parser
la sigue devolviendo en el turno siguiente (y lo hará, porque devuelve el estado
acumulado), se reintenta. El reintento lleva la misma `Idempotency-Key`.

**`TurnResult` en lugar de devolver solo `str`.** El enunciado no dice qué debe
devolver `handle_turn`. Devolver la respuesta junto con los datos parseados, la
acción, el `ActionOutcome` y el `ActionResult` permite:
- que un orquestador decida (por ejemplo, avisar si hay `FAILED`),
- que los tests comprueben comportamiento sin leer atributos privados,
- tener observabilidad.

**`ActionOutcome` como enum.** Los cuatro estados (`NOT_REQUIRED`, `DUPLICATE`,
`EXECUTED`, `FAILED`) son explícitos en lugar de deducirse de combinaciones de
`None` y booleanos.

**Logging con `logging`, no `print`.** Hay warnings cuando se descarta un dato
inválido o falla una integración, y un debug cuando se omite un duplicado.

## 8. Composición (`factory.py`)

**Composition root.** `AgentFactory` es el único sitio que sabe qué URL y qué
integración usa cada agente. Los agentes no leen variables de entorno ni
construyen sus dependencias. Esto permite cambiar de entorno (staging,
producción) sin tocar los agentes y usar el `FakeHttpClient` en tests y demo.

**El token se lee de una variable de entorno (`RINGR_API_TOKEN`).** Aunque el
enunciado da el token, un secreto no debe estar escrito en el código de la
aplicación: solo aparece en los tests y en el ejemplo de la demo.
`Settings.from_env` falla al arrancar si falta el token (fail fast), en lugar de
fallar más tarde con un 401.

## 9. Tests

68 tests en 0,1 s, sin red y sin `unittest.mock.patch`:

- `test_validation.py`: cada regla de validación, con casos límite (bool,
  NaN, `2026-02-30`, formatos alternativos).
- `test_integrations.py`: construcción exacta de la request (URL, método,
  headers, body), codificación, inyección de headers, errores de red y no 2xx,
  idempotency key y que el token no aparezca en `repr`.
- `test_debt_agent.py` / `test_assistance_agent.py`: las reglas de negocio de
  extremo a extremo (cuándo se actúa, duplicados, cambios de datos, datos
  inválidos, fallos y reintentos).
- `test_factory.py`: configuración y cableado.
- `test_extensibility.py`: un agente nuevo y una integración no HTTP en unas
  30 líneas. Es la prueba de que el diseño escala como pide el enunciado.

Estilo: Arrange / Act / Assert separados por líneas en blanco, un comportamiento
por test y nombres que describen la regla (`test_same_commitment_is_not_sent_twice`).

Las fixtures `make_debt_agent` y `make_assistance_agent` construyen un agente a
partir de solo la lista de salidas del parser, porque es lo único que cambia
entre escenarios.

## 10. Lo que dejaría para después

Ver la sección "Limitaciones y siguientes pasos" del README:
- persistir el estado de deduplicación,
- usar `Decimal` para el dinero,
- invertir el orden respuesta/acción,
- una política de reintentos con backoff o el patrón outbox,
- un cliente HTTP real.

Todo encaja en el diseño actual sin reescribir los agentes.
