# Ringr Agents

Agentes conversacionales que, turno a turno, responden al usuario, extraen datos
estructurados de la conversación y, si se cumplen las reglas de negocio,
ejecutan una acción sobre una API externa (simulada).

- **`DebtAgent`**: registra compromisos de pago (`commitment_date` + `committed_amount`)
  en `POST https://api.ringr.debt/v1/commitment`.
- **`AssistanceAgent`**: registra solicitudes para agentes humanos (`request`)
  en `POST https://api.ringr.assistance/v1/request`.

## Puesta en marcha

Requiere Python 3.10 o superior. No tiene dependencias en tiempo de ejecución.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                       # 68 tests
ruff check . && ruff format --check .

RINGR_API_TOKEN=ringr_test_token_9f3a2c1d python -m ringr_agents.demo
```

La demo ejecuta una conversación con cada agente e imprime, turno a turno, la
decisión tomada y las requests HTTP que se habrían enviado.

## Uso

```python
from ringr_agents.factory import AgentFactory, Settings
from ringr_agents.http_client import FakeHttpClient
from ringr_agents.models import ConversationModel, ParserModel

factory = AgentFactory(Settings.from_env(), FakeHttpClient())
agent = factory.debt_agent(
    ConversationModel(["¿Cuándo podría pagar?", "Registrado, gracias."]),
    ParserModel([
        {"commitment_date": None, "committed_amount": None},
        {"commitment_date": "2030-01-15", "committed_amount": 150},
    ]),
)

agent.handle_turn("Hola")                      # outcome = NOT_REQUIRED
result = agent.handle_turn("El 15 de enero pago 150 €")  # outcome = EXECUTED
result.reply                                   # "Registrado, gracias."
```

## Arquitectura

```
src/ringr_agents/
├── conversation.py      Conversation / Message: historial de la conversación
├── models.py            ConversationModel, ParserModel (simulados) + Protocols
├── validation.py        Validación y normalización de los campos parseados
├── actions.py           Action (abstracta), PaymentCommitment, AssistanceRequest
├── integrations.py      Integration (abstracta), HttpIntegration, BearerTokenAuth
├── http_client.py       HttpRequest/HttpResponse, HttpClient (abstracto), FakeHttpClient
├── agents/
│   ├── base.py          BaseAgent: ciclo de vida del turno, deduplicación
│   ├── debt.py          DebtAgent
│   └── assistance.py    AssistanceAgent
├── factory.py           Settings + AgentFactory: composición de dependencias
└── demo.py
```

Cada capa tiene una única responsabilidad y solo conoce a la de abajo a través
de una abstracción:

```
BaseAgent ──decide──▶ Action ──se entrega con──▶ Integration ──usa──▶ HttpClient
   │                                              (HttpIntegration)    (FakeHttpClient)
   ├── ConversationModel.answer_user()
   └── ParserModel.parse_data()
```

| Pieza | Qué sabe | Qué **no** sabe |
|---|---|---|
| ConversationModel / ParserModel | Responder al usuario / extraer los datos de la conversación | Reglas de negocio, que existe una API |
| Agente | Reglas de negocio: qué campos necesita, cuándo actuar | URLs, HTTP, tokens |
| Action | Los datos validados de la acción | Cómo ni a dónde se envía |
| Integration | Cómo construir la request: URL, headers, auth | Reglas de negocio |
| HttpClient | Cómo enviar bytes | Qué significan |
| AgentFactory | Qué integración y URL usa cada agente | — |

### Ciclo de un turno (`BaseAgent.handle_turn`)

```
ConversationModel  →  ParserModel  →  Agente  →  Acción  →  HttpIntegration
   (responde)        (da la ficha)   (decide)   (paquete)      (envía)
```

1. Se añade el mensaje del usuario a la conversación.
2. `ConversationModel.answer_user(conversation)` genera la respuesta, que también se añade.
3. `ParserModel.parse_data(conversation)` devuelve el dict con los datos extraídos.
4. `build_action(parsed_data)` valida, normaliza y decide. Es **el único método
   que implementa cada agente** y devuelve una `Action` o `None`.
5. Si la acción ya se ejecutó con éxito en esta conversación, no se reenvía (`DUPLICATE`).
6. Si no, se ejecuta a través de la `Integration`, que devuelve `EXECUTED` o `FAILED`.

El turno devuelve un `TurnResult` con la respuesta, los datos parseados, la acción
y su resultado (`NOT_REQUIRED`, `DUPLICATE`, `EXECUTED` o `FAILED`). Así quien
llama, sea un orquestador o los tests, puede saber qué pasó sin inspeccionar
estado interno.

## Decisiones principales

**Template Method en `BaseAgent`.** El orden de los pasos es igual para todos los
agentes y no debería poder romperse en una subclase. Por eso `handle_turn` es
concreto y las subclases solo implementan `build_action`. Un agente nuevo son unas
diez líneas (ver `tests/test_extensibility.py`).

**Inyección de dependencias y composition root.** Los agentes reciben los modelos y
la integración ya construidos. Toda la configuración (URLs, token, cliente HTTP)
se resuelve en un único sitio, `AgentFactory`. Esto hace todo testeable sin mocks
mágicos (`unittest.mock.patch` no aparece en ningún test).

**Las acciones son objetos de valor inmutables.** `PaymentCommitment` y
`AssistanceRequest` son `dataclass(frozen=True)`: dos acciones con los mismos datos
son iguales y hasheables. La deduplicación es un simple `set`.

**Deduplicación en dos niveles.**
- En el cliente: el agente recuerda las acciones ejecutadas **con éxito** y no las repite.
  Como se compara después de normalizar, `150` y `150.0` o `"Cambiar  tarifa"` y
  `"Cambiar tarifa"` cuentan como la misma acción.
- En el servidor: cada request lleva una cabecera `Idempotency-Key` determinista
  (hash de conversación + acción). Cubre el caso que la memoria del agente no
  puede cubrir: la request llega al servidor pero la respuesta se pierde (timeout)
  y se reintenta.

**Un fallo no rompe el turno.** `Integration.execute` devuelve los problemas de
entrega como `ActionResult(success=False)` en vez de lanzar una excepción. Si la
integración falla (error de red o respuesta no 2xx), el usuario recibe igualmente
su respuesta, el resultado es `FAILED` y la acción no se marca como ejecutada. Si
el parser la sigue devolviendo en el turno siguiente, se reintenta con la misma
`Idempotency-Key`. Una respuesta cuenta como éxito si `HttpResponse.ok` es cierto:

| `status_code` | `ok` |
|---|---|
| 200, 201 (cualquier 2xx) | `True` |
| 400, 500 (cualquier otro) | `False` |

**Modelos detrás de un `Protocol`.** El agente depende de `SupportsAnswerUser` y
`SupportsParseData`, no de las clases simuladas. Cualquier objeto con
`answer_user` o `parse_data` sirve, así que un cliente de LLM real se conecta sin
heredar de nada del proyecto ni tocar los agentes.

**Reloj inyectable.** `DebtAgent` recibe `today` (por defecto `date.today`) para
rechazar fechas pasadas. Los tests le pasan una fecha fija y no dependen del día
en que se ejecutan.

**El token no se filtra.** `BearerTokenAuth.token` y `Settings.api_token` usan
`field(repr=False)`, así que no aparecen al imprimir el objeto, en logs ni en
tracebacks.

**Validación estricta: un dato inválido equivale a un dato ausente.** Nunca se
ejecuta una acción con datos dudosos. Si el parser devuelve una fecha con otro
formato, un importe negativo o un tipo incorrecto, se registra un warning y el
campo se trata como `None`. El agente simplemente sigue la conversación hasta
obtener un dato válido.

**Integraciones abstractas.** El agente depende de `Integration`, no de HTTP. Una
integración por cola de mensajes, email o CRM no requiere tocar ningún agente
(ver `InMemoryQueueIntegration` en los tests). La autenticación también es
intercambiable (`Authenticator`).

## Ambigüedades del enunciado y cómo las he resuelto

| Punto | Decisión |
|---|---|
| Qué reciben `answer_user` y `parse_data` | La `Conversation` completa, como necesitaría un LLM real. Los simulados la ignoran. |
| ¿El parser devuelve solo lo del último mensaje o todo lo acumulado? | Todo lo acumulado. Es lo natural en un LLM con el historial y evita que el agente tenga que fusionar datos parciales. |
| Qué se considera "duplicado" | Misma acción con los mismos datos normalizados en la misma conversación. Si el usuario cambia el importe o pide otra cosa, es una acción nueva y sí se envía. |
| Qué va en el body | Los mismos datos normalizados que en los headers, en JSON. |
| Fechas pasadas | Un compromiso de pago con fecha anterior a hoy se considera inválido. Hoy sí es válido. |
| Importes | Positivos, finitos, redondeados a céntimos. `bool` se rechaza aunque en Python sea `int`. Strings como `"150"` se rechazan: el contrato dice `float`. |
| Valores `None` en headers | Se omiten. |

### Sobre enviar los datos parseados como headers

El enunciado pide enviar los datos del parser como headers "con los mismos
nombres". Lo he implementado así, pero tiene riesgos que en un caso real
comentaría con el equipo de la API:

- **Inyección de headers y codificación.** `request` es texto libre del usuario:
  puede llevar saltos de línea o caracteres no ASCII ("dirección"), y los headers
  solo admiten ASCII imprimible. Por eso los valores se normalizan (los espacios y
  saltos de línea se colapsan) y además se codifican en percent-encoding
  (`direcci%C3%B3n`). El body conserva el valor original y es la fuente de verdad.
- **Guiones bajos en los nombres.** Proxies como nginx descartan por defecto los
  headers con `_` (`underscores_in_headers off`), así que `commitment_date` podría
  no llegar. La convención sería `Commitment-Date` o `X-Commitment-Date`.
- **Tamaño.** Los servidores limitan el tamaño de los headers (unos 8 KB) y una
  solicitud larga podría superarlo.

Mi recomendación sería mandar los datos solo en el body.

## Limitaciones y siguientes pasos

- **Estado en memoria.** La deduplicación vive en la instancia del agente (una por
  conversación). Si la conversación pudiera continuar en otro proceso, ese estado
  tendría que persistirse (Redis, base de datos). La `Idempotency-Key` ya mitiga
  el riesgo en el servidor.
- **No es thread-safe.** Se asume que los turnos de una conversación son
  secuenciales, como en una llamada.
- **Dinero como `float`.** Se respeta el contrato del enunciado y se redondea a
  céntimos. En producción usaría `Decimal` internamente.
- **Respuesta antes que acción.** El enunciado fija el orden: responder, parsear,
  actuar. Por tanto la respuesta del turno no puede saber si la acción se ejecutó.
  Una mejora sería parsear antes de responder, o informar del resultado al
  `ConversationModel` en el turno siguiente.
- **Reintentos.** Solo se reintenta si el parser vuelve a devolver la acción en un
  turno posterior. Para acciones críticas convendría una política de reintentos
  con backoff en la integración, o una cola persistente (patrón outbox).
- **Cliente HTTP real.** Bastaría con implementar `HttpClient.send` con `httpx` o
  `requests`, traduciendo los errores de red a `HttpTransportError`.
