# Student Academic Assistant — Arquitectura (Fase 1 + Revisión 1.5)

Estado: **Fase 1 aprobada provisionalmente. Fase 1.5 (revisión técnica /
hardening) aplicada a este documento.** Todavía no se ha escrito código de
producción — sigue pendiente la implementación módulo por módulo, empezando
por el `BlackboardProvider`.

Prioridad de diseño en todo el sistema: **reliability > security >
maintainability > automation**.

## Registro de cambios — Revisión 1.5

Esta revisión no cambia las decisiones de la Fase 1, las endurece:

- Se agrega una sección dedicada de **máquina de estados con enforcement
  técnico** (código + trigger de base de datos), en vez de depender de que
  un prompt de Claude "se porte bien".
- Se separa explícitamente qué componentes son **agentes de IA** y cuáles
  son **servicios deterministas** (no todo lo que "hace algo" es un agente
  de Claude).
- Se define una **matriz de permisos de mínimo privilegio** por agente:
  ningún agente de IA tiene permiso de escritura sobre `Assignment.status`.
  Ese permiso es exclusivo de código determinista (`PipelineOrchestrator` y
  el endpoint de revisión humana).
- Se agrega la abstracción `BlackboardProvider` con `PlaywrightBlackboardProvider`
  como única implementación real por ahora, dejando el lugar para un futuro
  `OfficialBlackboardProvider` sin inventar su forma.
- Se agregan tablas de base de datos que faltaban: `AuditLog`, `AgentRun`,
  `AssignmentChangeLog`, `Source` (provenance).
- Se agregan secciones de **observability**, **failure recovery** y **human
  review UX** como secciones propias en vez de notas sueltas.
- Se aclara el alcance exacto del `Student Writing Style Agent`: solo puede
  tocar `Draft.content`, nunca instructions/rubric/citas/datos factuales —
  y esto se refuerza con permisos de base de datos, no solo con el prompt.

---

## 1. Análisis de requerimientos

Requerimientos funcionales clave:

- Detectar cursos y actividades académicas (assignments, quizzes, projects,
  discussions, announcements relevantes) en Blackboard.
- Filtrar lo que vence en los próximos 7 días.
- Extraer datos estructurados de cada actividad (curso, título, descripción,
  fecha de entrega, instrucciones, adjuntos, links, rubric, puntos máximos).
- Sincronizar fechas con Google Calendar sin tocar eventos existentes.
- Priorizar el trabajo con un score explicable.
- Preparar material de apoyo (resumen, checklist, research, outline, draft,
  cálculos, citas) usando Claude.
- Persistir todo el progreso y el estado de cada assignment.
- Notificar cuando algo esté listo para revisión.
- Requerir aprobación humana explícita antes de cualquier entrega.
- **Nunca** enviar un assignment automáticamente.

Requerimientos no funcionales clave:

- El scraper de Blackboard debe ser **read-only**.
- Resiliencia ante cambios de UI, timeouts, sesiones expiradas, MFA.
- Ninguna contraseña de Blackboard en texto plano.
- Todo el flujo debe poder revisarse desde el teléfono.
- El texto generado por IA debe sonar como lo escribiría un estudiante de
  tercer semestre, no como IA (sección 10).

Flujo completo validado en esta revisión (ver sección 4 para el detalle
técnico de cada flecha):

```
BLACKBOARD
   ↓
DISCOVERY            (status = DISCOVERED)
   ↓
PLANNING             (status = PLANNED)
   ↓
PREPARATION          (status = IN_PROGRESS: research + draft + citations)
   ↓
QUALITY CHECK        (gate interno dentro de IN_PROGRESS, ver 4.2)
   ↓
DRAFT_READY          (status = DRAFT_READY)
   ↓
WAITING_FOR_REVIEW   (status = WAITING_FOR_REVIEW)
   ↓
USER NOTIFICATION    (Notification creada automáticamente al entrar aquí)
   ↓
HUMAN REVIEW         (UI de revisión, sin cambio de estado todavía)
   ↓
USER APPROVAL        (status = APPROVED, requiere Review humano registrado)
   ↓
FINAL ACTION         (status = SUBMITTED — manual, no implementado aún)
```

El sistema **nunca** se salta `WAITING_FOR_REVIEW`. Ningún camino en el
código permite llegar a `APPROVED` o `SUBMITTED` sin pasar por ahí — esto se
verifica en la sección 4 con el mecanismo técnico, no solo con esta
descripción.

---

## 2. Arquitectura propuesta

Monolito modular (no microservicios: para un sistema de un solo usuario, los
microservicios añaden complejidad operativa sin beneficio real).

```
Blackboard (LMS)
      │  read-only, vía BlackboardProvider
      ▼
BlackboardParserService  ──►  BlackboardIngestionAgent  ──► DISCOVERED
      (determinista)              (determinista)
                                        │
                                        ▼
                              PipelineOrchestrator (determinista)
                                        │
                     ┌──────────────────┼───────────────────┐
                     ▼                  ▼                    ▼
              PlanningAgent (IA)  ResearchAgent (IA)   CalendarSyncService
              PLANNED→IN_PROGRESS                       (determinista)
                                        │
                                        ▼
                              DraftAgent (IA, writing style)
                                        │
                                        ▼
                              CitationAgent (IA + validación determinista)
                                        │
                                        ▼
                              QualityCheckAgent (IA) → reporte
                                        │  (leído por el orchestrator,
                                        │   NO escribe status directamente)
                                        ▼
                     PipelineOrchestrator: si aprueba → DRAFT_READY
                                        │
                                        ▼
                     PipelineOrchestrator: → WAITING_FOR_REVIEW
                                        │
                                        ▼
                              NotificationService (determinista)
                                        │
                                        ▼
                              Human Review UI  ──(manual)──► Review row
                                        │
                                        ▼
                     API /review/approve (auth humana) → APPROVED
                                        │
                                        ▼
                     FINAL ACTION (manual, fuera de alcance hoy) → SUBMITTED
```

Idea clave de esta revisión: **los agentes de IA nunca escriben
`Assignment.status`.** Solo el `PipelineOrchestrator` (código determinista)
y el endpoint `/review/approve` (requiere sesión humana autenticada) tienen
permiso de escritura sobre esa columna. Detalle completo en la sección 4.

Componentes principales:

| Módulo | Tipo | Responsabilidad |
|---|---|---|
| `blackboard/providers/` | determinista | Abstracción `BlackboardProvider` + implementaciones |
| `blackboard/parser.py` | determinista | HTML → DTOs normalizados |
| `ingestion/` | determinista | DTOs → filas DB, dedupe, change log |
| `pipeline/orchestrator.py` | determinista | Único escritor de `Assignment.status` (excepto `/review/approve`) |
| `ai/` | IA (Claude) | Planning, Research, Draft, Citation, QualityCheck |
| `calendar_sync/` | determinista | Google Calendar |
| `notifications/` | determinista | Telegram |
| `review/` | determinista + humano | UI y endpoint de aprobación |
| `observability/` | determinista | AgentRun, AuditLog, logging estructurado |
| `db/` | — | Persistencia |

---

## 3. Estructura de carpetas propuesta

```
school-agent/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── models/
│   │   │   └── migrations/            # incluye el trigger de sección 4.3
│   │   ├── schemas/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── courses.py
│   │   │       ├── assignments.py
│   │   │       ├── calendar.py
│   │   │       ├── review.py          # único lugar que puede llegar a APPROVED
│   │   │       └── notifications.py
│   │   ├── blackboard/
│   │   │   ├── providers/
│   │   │   │   ├── base.py            # BlackboardProvider (ABC)
│   │   │   │   ├── playwright_provider.py
│   │   │   │   └── official_provider.py  # stub, NotImplementedError
│   │   │   ├── auth.py
│   │   │   ├── browser.py
│   │   │   ├── parser.py
│   │   │   └── dto.py
│   │   ├── ingestion/
│   │   │   └── blackboard_ingestion_agent.py
│   │   ├── pipeline/
│   │   │   ├── orchestrator.py
│   │   │   └── state_machine.py       # ALLOWED_TRANSITIONS, sección 4
│   │   ├── ai/
│   │   │   ├── client.py
│   │   │   ├── planning_agent.py
│   │   │   ├── research_agent.py
│   │   │   ├── draft_agent.py
│   │   │   ├── citation_agent.py
│   │   │   ├── quality_check_agent.py
│   │   │   └── writing_style.py
│   │   ├── calendar_sync/
│   │   │   └── google_calendar.py
│   │   ├── notifications/
│   │   │   └── telegram.py
│   │   └── observability/
│   │       ├── agent_run.py
│   │       └── audit_log.py
│   ├── tests/
│   │   ├── blackboard/fixtures/
│   │   ├── pipeline/                  # tests de la máquina de estados
│   │   ├── ai/
│   │   └── calendar_sync/
│   ├── alembic/
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── dashboard/
│   │   └── review/[assignmentId]/
│   └── components/
├── docs/
├── ARCHITECTURE.md
└── README.md
```

Sigue siendo estructura propuesta, no creada como código todavía.

---

## 4. Máquina de estados y "Hard Stop" (enforcement técnico)

Este es el punto central de la revisión: la restricción de aprobación humana
**no depende de un prompt**. Hay tres capas independientes, cualquiera de
las cuales por sí sola ya bloquea el bypass.

### 4.1 Estados (sin cambios respecto a Fase 1)

```
DISCOVERED → PLANNED → IN_PROGRESS → DRAFT_READY → WAITING_FOR_REVIEW
→ APPROVED → SUBMITTED → ARCHIVED
```

Mapeo contra el diagrama conceptual del punto 1: `QUALITY CHECK` no es un
estado nuevo en el enum — es un gate interno que corre dentro de
`IN_PROGRESS` y decide si se puede avanzar a `DRAFT_READY`. `USER
NOTIFICATION` y `HUMAN REVIEW` tampoco son estados: son efectos/lecturas
alrededor de `WAITING_FOR_REVIEW`. `USER APPROVAL` = transición a
`APPROVED`. `FINAL ACTION` = transición a `SUBMITTED`.

### 4.2 Capa 1 — Tabla de transiciones en código (única función de escritura)

```python
ALLOWED_TRANSITIONS = {
    DISCOVERED:         {PLANNED, ARCHIVED},
    PLANNED:            {IN_PROGRESS, ARCHIVED},
    IN_PROGRESS:        {IN_PROGRESS, DRAFT_READY, ARCHIVED},  # retry de quality check
    DRAFT_READY:        {IN_PROGRESS, WAITING_FOR_REVIEW},     # nunca SUBMITTED
    WAITING_FOR_REVIEW: {IN_PROGRESS, APPROVED},                # "request changes" regresa
    APPROVED:           {SUBMITTED, ARCHIVED},
    SUBMITTED:          {ARCHIVED},
    ARCHIVED:           set(),
}

def transition_assignment_status(assignment, new_status, actor: Actor) -> None:
    if new_status not in ALLOWED_TRANSITIONS[assignment.status]:
        raise IllegalTransitionError(assignment.status, new_status)
    if new_status == APPROVED and actor.kind != "user":
        raise ForbiddenActorError("only an authenticated human can approve")
    if new_status == SUBMITTED and actor.kind != "user":
        raise ForbiddenActorError("only an authenticated human can trigger final action")
    ...  # commit + AuditLog + AssignmentStatusHistory en la misma transacción
```

`transition_assignment_status()` es la **única** función en todo el
backend con permiso de escribir `assignments.status`. Ningún agente de IA
la llama directamente para llegar a `APPROVED`/`SUBMITTED`: solo la llama
el `PipelineOrchestrator` (para DISCOVERED/PLANNED/IN_PROGRESS/DRAFT_READY/
WAITING_FOR_REVIEW/ARCHIVED) y el endpoint `POST /assignments/{id}/review/approve`
(único caller autorizado para APPROVED, y en el futuro para SUBMITTED si se
implementa un final-action explícito).

Los agentes de IA (`PlanningAgent`, `ResearchAgent`, `DraftAgent`,
`CitationAgent`, `QualityCheckAgent`) **no importan ni llaman esta
función**. Solo escriben en sus propias tablas (`Research`, `Draft`,
`Citation`, `AgentRun`) y devuelven un resultado; es el
`PipelineOrchestrator` quien decide, en base a ese resultado, si mueve el
estado.

### 4.3 Capa 2 — Trigger de base de datos (defensa independiente de la app)

Aunque la Capa 1 tenga un bug, la base de datos rechaza la transición
igual. Trigger `BEFORE UPDATE ON assignments`:

```sql
CREATE OR REPLACE FUNCTION enforce_assignment_status_transition()
RETURNS trigger AS $$
DECLARE
  actor text := current_setting('app.actor', true);  -- seteado por la app: 'user:<id>' | 'agent:<name>' | 'system'
BEGIN
  IF NEW.status = OLD.status THEN
    RETURN NEW;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM allowed_status_transitions
    WHERE from_status = OLD.status AND to_status = NEW.status
  ) THEN
    RAISE EXCEPTION 'illegal transition % -> %', OLD.status, NEW.status;
  END IF;

  IF NEW.status = 'APPROVED' AND (actor IS NULL OR actor NOT LIKE 'user:%') THEN
    RAISE EXCEPTION 'APPROVED requires an authenticated human actor';
  END IF;

  IF NEW.status = 'SUBMITTED' THEN
    IF actor IS NULL OR actor NOT LIKE 'user:%' THEN
      RAISE EXCEPTION 'SUBMITTED requires an authenticated human actor';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM reviews
      WHERE assignment_id = NEW.id AND decision = 'approved'
    ) THEN
      RAISE EXCEPTION 'SUBMITTED requires a recorded human approval';
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_assignment_status_transition
BEFORE UPDATE OF status ON assignments
FOR EACH ROW EXECUTE FUNCTION enforce_assignment_status_transition();
```

`allowed_status_transitions` es la tabla espejo de `ALLOWED_TRANSITIONS`,
poblada por migración, así queda auditable y no depende de que el código
Python y la base de datos nunca se desincronicen sin que salte un error.

Esto bloquea **incluso un `UPDATE` manual por SQL/consola de admin/bug en
una migración futura** que intente saltarse `WAITING_FOR_REVIEW`.

### 4.4 Capa 3 — Roles de base de datos (mínimo privilegio real)

- Rol `app_agent_worker` (usado por los agentes de IA y el ingestion): sin
  `UPDATE` sobre `assignments.status` en absoluto — solo `SELECT` sobre
  `assignments`, y `INSERT`/`UPDATE` sobre `research`, `drafts`,
  `citations`, `agent_runs`.
- Rol `app_orchestrator`: `UPDATE` sobre `assignments.status`, pero el
  trigger de 4.3 igual le bloquea `APPROVED`/`SUBMITTED` porque no puede
  setear `app.actor` como `user:...` (solo la capa de API autenticada
  puede hacerlo, después de validar la sesión del usuario).
- Rol `app_api` (atiende `/review/approve`): el único que setea
  `app.actor = 'user:<id>'` tras autenticar la sesión, y por lo tanto el
  único capaz de producir un `UPDATE` que el trigger acepte para `APPROVED`.

Con esto, "un agente puede pasar directamente de `DRAFT_READY` a
`SUBMITTED`" es falso en tres niveles distintos e independientes: no tiene
la función para hacerlo (4.2), el trigger lo rechaza aunque lo intente por
SQL crudo (4.3), y ni siquiera tiene el rol de base de datos necesario para
intentarlo (4.4).

---

## 5. Esquema de base de datos (PostgreSQL)

Relaciones:

```
User (1) ── (N) Course
Course (1) ── (N) Assignment
Assignment (1) ── (N) AssignmentAttachment
Assignment (1) ── (N) AssignmentStatusHistory
Assignment (1) ── (N) AssignmentChangeLog
Assignment (1) ── (N) CalendarEvent
Assignment (1) ── (N) Research ── (N) Source
Assignment (1) ── (N) Draft ── (N) Citation
Assignment (1) ── (N) Notification
Assignment (1) ── (N) Review
Assignment (1) ── (N) AgentRun
(*)        (N) ── (N) AuditLog   (genérico, cualquier entidad)
```

Tablas de Fase 1 (sin cambios): `User`, `Course`, `Assignment`,
`AssignmentAttachment`, `CalendarEvent`, `Research`, `Draft`, `Citation`,
`Notification`, `Review`. Ver el documento original para sus campos; se
mantienen igual.

Renombre: la tabla de historial de estados pasa de `AssignmentStatus` a
**`AssignmentStatusHistory`** para no confundirla con el campo
`Assignment.status`:

`id, assignment_id, from_status, to_status, actor (user:<id>|agent:<name>|system), changed_at, note`

Tablas nuevas de esta revisión:

**AgentRun** — respuesta a observability (sección 7)
`id, agent_name, assignment_id, run_type, triggered_by (scheduler|manual|orchestrator),
started_at, finished_at, status (success|failure), input_ref, output_ref,
error_message, tokens_used`
`input_ref`/`output_ref` son punteros (id de `Research`/`Draft`/etc.) o un
resumen corto, no el contenido completo duplicado — evita inflar logs con
información que ya vive en su tabla dueña.

**AuditLog** — genérico, para cualquier acción sensible fuera del ciclo de
vida normal de un agente (cambios de config, borrado de eventos de
calendar, decisiones de review)
`id, entity_type, entity_id, actor, action, reason, before_json, after_json, created_at`

**AssignmentChangeLog** — diffs de contenido detectados en Blackboard
(distinto del historial de *status*; esto es historial de *contenido*)
`id, assignment_id, field (due_date|points_possible|description|instructions),
old_value, new_value, detected_at`

**Source** — provenance explícito de research (antes vivía solo como JSON
suelto dentro de `Research`)
`id, research_id, url, title, retrieved_at, verified (bool), notes`

Ajustes a tablas existentes:

- `Draft`: se aclara que es **append-only** — cada regeneración crea una
  fila nueva con `version` incrementado; nunca se hace `UPDATE` sobre una
  fila de draft existente, para preservar historial de versiones.
- `Review`: `decision` values = `approved | changes_requested`; se agrega
  `reviewed_by_actor` (debe ser siempre `user:<id>`, nunca `agent:*` — el
  trigger de la sección 4.3 depende de esto).

Regla dura (repetida de la sección 4, ahora también a nivel de esquema):
`assignments.status = 'SUBMITTED'` requiere `EXISTS (SELECT 1 FROM reviews
WHERE assignment_id = assignments.id AND decision = 'approved')`,
verificado por trigger, no por convención de la aplicación.

---

## 6. APIs propuestas (backend, FastAPI)

Sin cambios de fondo respecto a Fase 1, con una aclaración:

```
GET    /courses
GET    /courses/{id}/assignments

GET    /assignments?status=&priority=&due_within_days=
GET    /assignments/{id}
POST   /assignments/sync

GET    /assignments/{id}/research
GET    /assignments/{id}/draft
POST   /assignments/{id}/draft/regenerate

POST   /assignments/{id}/review/approve       # único endpoint que puede producir APPROVED
POST   /assignments/{id}/review/request-changes

GET    /calendar/status
POST   /calendar/sync

GET    /notifications
POST   /notifications/{id}/read
```

Sigue sin existir ningún endpoint de submit. `/review/approve` autentica la
sesión del usuario y hace `SET LOCAL app.actor = 'user:<id>'` antes de
llamar `transition_assignment_status(..., APPROVED, actor)`, para que el
trigger de la sección 4.3 pueda verificarlo. Si en el futuro se agrega un
endpoint de `final-action`, seguiría el mismo patrón y seguiría siendo una
acción separada, nunca disparada por `/review/approve`.

---

## 7. Agentes: responsabilidades y permisos de mínimo privilegio

Se separan explícitamente **agentes de IA** (llaman a Claude) de
**servicios deterministas** (código normal, sin IA), porque no todo lo que
"hace algo" en el pipeline necesita ser un agente de Claude.

| # | Componente | Tipo | Input | Output | DB access | Tools | NO puede hacer |
|---|---|---|---|---|---|---|---|
| 1 | `BlackboardParserService` | Determinista | HTML/DOM crudo del `BlackboardProvider` | DTOs normalizados (Course/Assignment) | Ninguno (retorna DTOs al caller) | `BlackboardProvider` (read-only) | Escribir Blackboard, escribir DB |
| 2 | `BlackboardIngestionAgent` | Determinista | DTOs del parser | Filas `Course`/`Assignment`/`AssignmentAttachment`, `AssignmentChangeLog`, status inicial `DISCOVERED` | WRITE `Course`, `Assignment` (solo campos de contenido, no status más allá de `DISCOVERED`/`ARCHIVED` por desaparición), `AssignmentAttachment`, `AssignmentChangeLog` | DB session | Escribir `CalendarEvent`, `Research`, `Draft`, `status=APPROVED/SUBMITTED`, cualquier submission |
| 3 | `PlanningAgent` | IA (Claude) | Assignment (instructions, rubric, due_date, points) | checklist, priority, estimated_hours, work_plan | READ `Assignment`, `Course`; WRITE `Assignment` (solo campos de planning), `AgentRun` | Claude API (texto, sin browsing) | WRITE `status`, `Draft`, `Research`, `Citation`, `CalendarEvent`, Blackboard |
| 4 | `ResearchAgent` | IA (Claude) | Instructions + rubric | `Research` + `Source` rows | READ `Assignment`; WRITE `Research`, `Source`, `AgentRun` | Claude API (+ búsqueda web si se habilita, registrando siempre la fuente) | WRITE `Draft`, `status`, `CalendarEvent`, Blackboard, submission |
| 5 | `DraftAgent` | IA (Claude, aplica Writing Style) | Instructions, `Research`, `Citation` requeridas | Nueva versión de `Draft` (append-only), marcadores `[PERSONAL OPINION NEEDED]` etc. | READ `Assignment`, `Research`; WRITE `Draft`, `AgentRun` | Claude API + reglas de `writing_style` | Modificar `instructions`/`rubric_json`/`Citation.source_text`, WRITE `status`, `CalendarEvent`, submission |
| 6 | `CitationAgent` | IA + validación determinista | `Draft.content`, `Source` | `Citation` rows, bibliografía formateada, flag `verified` | READ `Draft`, `Research`/`Source`; WRITE `Citation`, `AgentRun` | Claude API + validador de formato (determinista) | Reescribir la narrativa del draft, WRITE `status`, submission |
| 7 | `QualityCheckAgent` | IA (Claude) | `Draft`, `Citation`, rubric | Reporte estructurado (requisitos faltantes, cobertura de rubric, issues) guardado en `AgentRun.output_ref` | READ `Draft`, `Citation`, `Assignment`; WRITE **solo** `AgentRun` | Claude API | **WRITE `status` (ni siquiera `DRAFT_READY`) — el reporte lo lee el `PipelineOrchestrator`, que decide la transición** |
| 8 | `PipelineOrchestrator` | Determinista | Resultados de agentes vía `AgentRun` | Transiciones de `status` hasta `WAITING_FOR_REVIEW` (nunca `APPROVED`/`SUBMITTED`) | WRITE `assignments.status` (rol `app_orchestrator`, sin poder pasar el trigger para APPROVED/SUBMITTED) | `transition_assignment_status()` | Producir `APPROVED`/`SUBMITTED` (bloqueado por trigger + rol DB) |
| 9 | `NotificationService` | Determinista | Assignment entra a `WAITING_FOR_REVIEW` | `Notification` row + mensaje Telegram | READ `Assignment`; WRITE `Notification` | Telegram API | WRITE `status`, `Draft`, `Research`, submission |
| 10 | `CalendarSyncService` | Determinista | `Assignment.due_date`/status | `CalendarEvent` rows, llamadas create/update a Google Calendar | READ `Assignment`; WRITE `CalendarEvent` | Google Calendar API | `DELETE` eventos que no creó, WRITE `status`, Blackboard, submission |
| 11 | Endpoint `/review/approve` | Determinista + humano | Decisión del usuario en la UI | `Review` row + transición a `APPROVED` | WRITE `Review`; WRITE `assignments.status` (rol `app_api`, único que puede setear `app.actor='user:...'`) | `transition_assignment_status()` | Transicionar sin sesión humana autenticada, disparar `SUBMITTED` |

Nota sobre `QualityCheckAgent`: a diferencia de lo descrito en la Fase 1
("el QualityCheckAgent es el único que puede mover un assignment a
DRAFT_READY"), esta revisión lo corrige — **ningún agente de IA mueve
status**. `QualityCheckAgent` solo produce un veredicto; es el
`PipelineOrchestrator` (determinista) quien, al leerlo, decide si llama
`transition_assignment_status(..., DRAFT_READY, actor=agent:orchestrator)`.
Esto es justamente lo que exige el punto 3 de la revisión: separación de
responsabilidades real, no solo nominal.

---

## 8. Integración con Blackboard

Se mantiene sin cambios la comparación de opciones de la Fase 1 (REST API
oficial / Ultra APIs / Playwright / Chrome extension) y la recomendación:
preferir API oficial solo si se confirma acceso real; si no, Playwright de
forma modular y resiliente. No se inventan endpoints ni se asume que todas
las instituciones tienen la misma versión de Blackboard.

Lo que agrega esta revisión es la capa de abstracción pedida:

```python
class BlackboardProvider(ABC):
    def login(self) -> SessionHandle: ...
    def list_courses(self) -> list[CourseDTO]: ...
    def list_assignments(self, course_id: str) -> list[AssignmentDTO]: ...
    def get_assignment_detail(self, assignment_id: str) -> AssignmentDetailDTO: ...
    def download_attachment(self, url: str) -> bytes: ...
    def health_check(self) -> ProviderHealth: ...
```

- `PlaywrightBlackboardProvider(BlackboardProvider)`: única implementación
  real hoy, envuelve `auth.py`/`browser.py`/`parser.py` de la Fase 1.
- `OfficialBlackboardProvider(BlackboardProvider)`: stub que levanta
  `NotImplementedError`. Se implementa **solo si** confirmas que tu
  institución expone una API accesible para tu cuenta (ver checklist de
  información pendiente en la sección 16). No se escribe ningún endpoint
  supuesto mientras tanto.
- Selección vía config: `BLACKBOARD_PROVIDER_IMPL=playwright|official`. El
  resto del sistema (`BlackboardIngestionAgent` en adelante) solo conoce
  los DTOs, nunca el proveedor concreto — cambiar de Playwright a una API
  oficial el día de mañana no debería tocar nada más que esta capa.

El resto del diseño del módulo Playwright (`auth.py`, `browser.py`,
`courses.py`, `assignments.py`, `attachments.py`, `parser.py`, resiliencia
ante cambios de UI, read-only estricto) se mantiene igual que en la Fase 1.

---

## 9. Integración con Google Calendar

Se mantiene la base de la Fase 1 (OAuth2, scope mínimo, refresh token
cifrado, nunca borrar/modificar eventos ajenos) y se agrega el detalle que
pedía la revisión:

- **Timezone handling**: `due_date` se guarda en UTC en la base de datos
  junto con la `timezone` IANA del curso/usuario (ej. `America/Bogota`).
  La conversión a la timezone del usuario ocurre solo al construir el
  evento de Google Calendar, nunca se pierde la referencia UTC original.
- **Duplicate detection / reconciliation**: cada `CalendarEvent` guarda
  `google_event_id` y además se escribe
  `extendedProperties.private.assignment_id = <Assignment.id>` en el
  evento de Google. La sincronización busca primero por
  `google_event_id`; si por algún motivo se perdiera esa referencia local,
  usa `assignment_id` en `extendedProperties` como respaldo antes de crear
  uno nuevo — así nunca se duplica un evento aunque se pierda el puntero
  local.
- **Changed due dates**: detectado vía `AssignmentChangeLog` (sección 5),
  dispara `UPDATE` del evento existente (nunca delete+create, para no
  perder invitados/recordatorios que el usuario haya configurado a mano).
- **Cancelled assignments**: si un assignment pasa a `ARCHIVED` por haber
  desaparecido de Blackboard, el `CalendarEvent` correspondiente **no se
  borra automáticamente** — se marca como `pending_deletion` y se pide
  confirmación explícita al usuario (notificación + acción manual), igual
  que para cualquier borrado.
- Sigue sin existir ningún camino de código que borre o modifique un
  evento sin `extendedProperties.private.source =
  "student-academic-assistant"`.

---

## 10. Reglas de estilo de escritura (Student Writing Style Agent) — alcance

Se mantienen las reglas de estilo de la Fase 1 (natural, directo, nivel de
tercer semestre, sin muletillas de IA, sin intentar evadir detectores, sin
errores artificiales, marcadores `[PERSONAL OPINION NEEDED]` /
`[ADD YOUR EXPERIENCE]` / `[ADD YOUR EXAMPLE]` cuando falte información
personal).

Aclaración de alcance pedida en esta revisión — el estilo **solo** aplica a
`Draft.content` generado por `DraftAgent`. Nunca se aplica a:

| Campo | Por qué se muestra siempre verbatim |
|---|---|
| `Assignment.instructions` | Es lo que escribió el profesor; alterarlo cambiaría el significado de la tarea |
| `Assignment.rubric_json` | Criterio de evaluación real, no se reescribe |
| `Citation.source_text` / `Source.url` | Dato factual/bibliográfico, no texto de estilo |
| `Research.content` (citas textuales) | Contenido fuente, no redacción del estudiante |
| `Assignment.due_date` / `points_possible` | Datos, no prosa |

Esto no depende solo de instruir al `DraftAgent` a "no tocar esos campos":
según la matriz de permisos de la sección 7, `DraftAgent` tiene acceso
`READ` (no `WRITE`) sobre `Assignment`, `Research` y `Citation` — no tiene
el permiso de base de datos para modificarlos aunque un prompt inyectado
intentara pedírselo.

---

## 11. Modelo de seguridad — threat model

| Activo | Dónde se guarda | Protección | Principal amenaza | Mitigación |
|---|---|---|---|---|
| Password de Blackboard | **No se guarda, en ningún lado** | N/A | N/A | Login manual (incluye MFA) cada vez que se necesita, nunca capturado por el sistema |
| Sesión de Blackboard (`storage_state`) | Columna cifrada en DB | AES-256 (`cryptography.Fernet`), clave fuera del repo (secret manager / env) | Breach de DB → session hijack | TTL corto, re-login manual al expirar, acceso a DB restringido por rol |
| Refresh token de Google OAuth | Columna cifrada en DB | Igual que arriba | Leak → acceso no autorizado al calendar | Scope mínimo (`calendar.events`), revocable, cifrado |
| Claude API key | Variable de entorno / secret manager | Nunca en repo ni en logs | Leak → abuso de billing | Secret manager, rotación periódica |
| Credenciales de DB | Variable de entorno / secret manager | Nunca en repo | Breach total de datos | Roles de mínimo privilegio (sección 4.4), red restringida |
| Adjuntos descargados de Blackboard | Filesystem/object storage privado | Acceso controlado, sin URLs públicas | Podrían contener info de otros estudiantes si son materiales compartidos | Almacenamiento privado, nunca expuesto públicamente |
| Drafts generados | DB | Acceso controlado (single user) | Confundirse y tratarlo como entrega final | UI marca todo como borrador; el gate de aprobación (sección 4) lo impide estructuralmente |

---

## 12. Observability

Cada ejecución relevante debe poder responder WHO / WHAT / WHEN / WHY /
INPUT / OUTPUT / RESULT / ERROR. Dos tablas cubren esto (sección 5):

- **`AgentRun`**: una fila por cada corrida de cualquier agente (IA o
  determinista relevante). Responde WHAT (agent_name/run_type), WHEN
  (started_at/finished_at), INPUT/OUTPUT (referencias, no duplicar
  contenido completo), RESULT (status), ERROR (error_message).
- **`AuditLog`**: una fila por cada acción sensible sobre cualquier
  entidad (transición de status, aprobación, borrado de evento de
  calendar, envío de notificación). Responde WHO (actor), WHY (reason),
  antes/después (`before_json`/`after_json`).

Ejemplos de lo que debe poder reconstruirse a partir de estas tablas
(igual que los ejemplos que diste):

```
[AgentRun#4821] BlackboardIngestionAgent detectó "Case Study" (course=Accounting 301) a las 14:03. RESULT=success.
[AssignmentChangeLog#77] due_date: 2026-08-10 23:59 → 2026-08-12 23:59 (detectado 14:03).
[AuditLog#312] CalendarSyncService actualizó google_event_id=abc123 por cambio de due_date. actor=agent:calendar_sync.
[AgentRun#4830] DraftAgent generó Draft#9 v2 para Assignment#55. RESULT=success. tokens_used=3120.
[AuditLog#315] NotificationService envió Telegram a user:1 sobre Assignment#55 (WAITING_FOR_REVIEW).
[AuditLog#320] Review#12 creada: decision=approved, actor=user:1, reviewed_at=...
[AssignmentStatusHistory#88] DRAFT_READY → WAITING_FOR_REVIEW, actor=agent:orchestrator.
[AssignmentStatusHistory#89] WAITING_FOR_REVIEW → APPROVED, actor=user:1.
```

Redacción: `input_ref`/`output_ref` en `AgentRun` son punteros o resúmenes
cortos, no el contenido completo. Nunca se loguea texto plano de:
password de Blackboard (nunca existe), `storage_state`, refresh tokens,
Claude API key, credenciales de DB. Un filtro de logging redacta por
nombre de campo conocido antes de escribir a stdout/agregador de logs.

---

## 13. Failure recovery

Regla general, válida para todos los casos de la tabla: **un error nunca
se interpreta como autorización para continuar automáticamente**. El
assignment se queda en su último estado válido conocido, se registra en
`AgentRun`/`AuditLog`, y solo se notifica al usuario si es algo que
requiere su atención.

| Escenario | Comportamiento |
|---|---|
| Blackboard no disponible | Reintentos acotados con backoff (ej. 3x); si sigue fallando, se salta el ciclo, `AgentRun.status=failure`, no se toca ningún assignment existente |
| Login fallido | Reintentos acotados, luego se marca la sesión inválida y se notifica al usuario para re-login manual; el pipeline de ingestion se pausa, no se inventa data |
| MFA requerido | Login headful con timeout de espera (ej. 5 min) para completarlo manualmente; si expira, falla de forma segura y notifica |
| Sesión expirada a mitad de corrida | La corrida en curso se aborta limpiamente (transacción por assignment, sin escrituras parciales), se notifica, no se archiva nada solo por el fallo de scraping |
| Falla al parsear un assignment (selector roto) | Se salta ese assignment puntual, se loguea con snapshot de HTML para debug, continúa con el resto, se notifica "N assignments no se pudieron leer" |
| Falla de Google Calendar API | Reintentos con backoff; si persiste, se salta la sincronización de ese ciclo sin afectar `Assignment.status`; solo se notifica si la falla persiste varios ciclos seguidos |
| Falla de Claude API / timeout | `AgentRun.status=failure`, el assignment se queda en `IN_PROGRESS`, se reintenta en el siguiente ciclo; nunca se inventa un output "por si acaso" |
| Assignment duplicado | Idempotente por `blackboard_assignment_id` (upsert), nunca por título |
| Due date cambiada | `AssignmentChangeLog` + actualización de `CalendarEvent` (update, no delete+create) + notificación |
| Assignment eliminado/cancelado en Blackboard | Se marca `ARCHIVED` con nota (nunca se borra de la DB); el evento de calendar asociado requiere confirmación explícita antes de borrarse |
| Adjunto corrupto/malformado | Se salta ese adjunto puntual, se loguea, no falla la ingestion completa del assignment |
| Timeout genérico en cualquier llamada externa | Toda llamada externa (Blackboard, Google, Claude) tiene timeout explícito + reintentos acotados + estado de fallo seguro; nunca se asume éxito por timeout |

---

## 14. Human-in-the-loop UX

**Notificación** (formato, igual al ejemplo que diste):

```
Accounting 301 — Case Study
Due: Aug 12, 11:59 PM
Priority: HIGH
Estimated time: 2h
Draft ready for review.
Open review →
```

Campos siempre presentes: course, assignment, deadline, priority,
estimated remaining time, link, status.

**Pantalla de revisión**, debe mostrar todo junto y fácil de navegar desde
el teléfono:

1. Original instructions (verbatim)
2. Rubric (verbatim)
3. Research generado + fuentes (`Source`)
4. Outline
5. Draft (con marcadores `[PERSONAL OPINION NEEDED]` etc. resaltados)
6. Quality checks (reporte de `QualityCheckAgent`: qué cumple, qué falta)
7. Missing information / sections requiring personal input (lista aparte,
   no solo inline, para que sea rápido ver qué falta antes de aprobar)
8. Checklist de requisitos (de `PlanningAgent`)
9. Secciones marcadas como "AI-generated" claramente distinguidas del
   contenido verbatim de instructions/rubric/citas

Botón **"APPROVE FOR SUBMISSION"**: llama a `/review/approve`, crea la fila
`Review(decision=approved, reviewed_by_actor=user:<id>)` y transiciona a
`APPROVED` (sección 4). No dispara ninguna entrega — solo desbloquea el
flujo siguiente, que hoy no existe como automatización.

---

## 15. Testing

Se agregan a los tests de Fase 1:

- **State machine**: cada transición válida e inválida de
  `ALLOWED_TRANSITIONS` (matriz completa, no solo el caso feliz).
- **Permission boundaries**: cada agente de IA intentando escribir fuera
  de su tabla permitida debe fallar por permisos de rol de DB, no solo por
  falta de método en el código (test de integración contra Postgres real
  con los roles de la sección 4.4).
- **Blackboard extraction**: fixtures de HTML, duplicados, HTML
  malformado, sesión expirada (Fase 1, sin cambios).
- **Calendar sync**: no duplica, no borra eventos ajenos, reconcilia por
  `google_event_id` y por `extendedProperties.assignment_id` como
  respaldo, maneja timezone correctamente.
- **Deadline changes**: `AssignmentChangeLog` se crea, `CalendarEvent` se
  actualiza (no se recrea), notificación se envía.
- **Notifications**: formato correcto, se dispara exactamente una vez al
  entrar a `WAITING_FOR_REVIEW`, no se reenvía en cada ciclo del scheduler.
- **Agent failures**: cada modo de la tabla de la sección 13 tiene un test
  que verifica que el assignment queda en el último estado válido y que
  `AgentRun.status=failure` queda registrado.
- **Human approval enforcement** (el test central que pediste):

```python
def test_draft_ready_to_submitted_is_impossible_without_approval():
    assignment = make_assignment(status=DRAFT_READY)

    # 1) vía la función de la app
    with pytest.raises(IllegalTransitionError):
        transition_assignment_status(assignment, SUBMITTED, actor=Actor("agent:quality_check"))

    # 2) vía SQL crudo, saltándose la app por completo
    with pytest.raises(DBIntegrityError):  # el trigger de 4.3 lo rechaza
        db.execute(
            "UPDATE assignments SET status='SUBMITTED' WHERE id=:id",
            {"id": assignment.id},
        )

    # 3) vía el endpoint de aprobación, sin una Review previa
    response = client.post(f"/assignments/{assignment.id}/review/approve")
    # aprueba (WAITING_FOR_REVIEW -> APPROVED), pero no existe endpoint
    # de submit que pueda usarse a continuación en esta fase — se verifica
    # que no hay ningún camino HTTP hacia SUBMITTED
    assert not any(route.path.endswith("/submit") for route in app.routes)
```

---

## 16. ARCHITECTURE STATUS

**CHANGES REQUIRED → aplicados en este documento.** Ver reporte final más
abajo en la respuesta (fuera de este archivo) para el detalle de qué se
encontró y qué se corrigió.

## Siguiente paso

Falta implementación real. Para arrancar por el `BlackboardProvider`
(`PlaywrightBlackboardProvider`) sigue haciendo falta que confirmes:

1. URL base de tu Blackboard (ej. `https://universidad.blackboard.com`).
2. Si es Blackboard Learn **Ultra** o **Original Experience**.
3. Si tu institución tiene portal de desarrollador Blackboard/Anthology
   con client credentials accesibles para tu cuenta (si no lo sabes, lo
   más probable es que no — vamos directo a `PlaywrightBlackboardProvider`).
4. Cómo inicias sesión: usuario/contraseña directo, o SSO (Okta/Azure
   AD/Shibboleth/otro) con MFA.
5. Capturas de pantalla (sin datos sensibles) de la vista de cursos y de
   un assignment, para diseñar los selectores del parser sin adivinar.

No se escribe código de producción hasta que apruebes explícitamente esta
revisión.
