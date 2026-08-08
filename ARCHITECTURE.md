# Student Academic Assistant — Propuesta de Arquitectura (Fase 1)

Estado: **propuesta, pendiente de aprobación**. No se ha escrito código de
producción todavía. Este documento cubre los 10 puntos solicitados antes de
construir nada.

Prioridad de diseño en todo el sistema: **reliability > security >
maintainability > automation**.

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

- El scraper de Blackboard debe ser **read-only** (nunca modifica grades,
  submissions, ni configuración del curso).
- Resiliencia ante cambios de UI, timeouts, sesiones expiradas, MFA.
- Ninguna contraseña de Blackboard en texto plano.
- Todo el flujo debe poder revisarse desde el teléfono.
- El texto generado por IA debe sonar como lo escribiría un estudiante de
  tercer semestre, no como IA (ver `docs/writing-style.md` más abajo, sección 9).

Restricción crítica de flujo (no negociable, y es el criterio contra el que
se valida cualquier diseño posterior):

```
DISCOVERY → PLANNING → PREPARATION → REVIEW → USER APPROVAL
```

Nunca `DISCOVERY → AUTOMATIC SUBMISSION`. El botón "APPROVE FOR SUBMISSION"
solo registra la aprobación; no dispara un envío automático salvo que en el
futuro se configure explícitamente una integración de entrega (fuera de
alcance por ahora).

---

## 2. Arquitectura propuesta

Arquitectura modular, orientada a servicios dentro de un mismo backend
(monolito modular, no microservicios — para un sistema de un solo usuario,
microservicios añaden complejidad operativa sin beneficio real).

```
                         ┌─────────────────────┐
                         │   Blackboard (LMS)   │
                         └──────────┬───────────┘
                                    │ read-only
                         ┌──────────▼───────────┐
                         │ Blackboard Integration │  (auth, courses,
                         │        Module          │   assignments, parser)
                         └──────────┬───────────┘
                                    │ normalized Assignment objects
                         ┌──────────▼───────────┐
                         │  Assignment Manager    │  (summary, checklist,
                         │        Module          │   priority, work plan)
                         └──────────┬───────────┘
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                 ┌─────────────┐ ┌────────┐ ┌───────────────┐
                 │ Google       │ │ AI      │ │ Notification  │
                 │ Calendar Sync│ │ Layer   │ │ Module        │
                 └─────────────┘ │(Claude) │ └───────────────┘
                                  └────┬────┘
                                       ▼
                              ┌─────────────────┐
                              │ Research/Draft/  │
                              │ Quality Check     │
                              └────────┬─────────┘
                                       ▼
                              ┌─────────────────┐
                              │ WAITING_FOR_REVIEW│
                              └────────┬─────────┘
                                       ▼
                              ┌─────────────────┐
                              │  Human Review UI  │
                              └────────┬─────────┘
                                       ▼ (manual)
                              ┌─────────────────┐
                              │     APPROVED      │
                              └────────┬─────────┘
                                       ▼ (siempre manual)
                              ┌─────────────────┐
                              │     SUBMITTED      │
                              └─────────────────┘
```

Componentes principales:

| Módulo | Responsabilidad |
|---|---|
| `blackboard/` | Autenticación, extracción read-only, normalización |
| `assignment_manager/` | Convierte assignments en trabajo accionable (checklist, prioridad, plan) |
| `calendar_sync/` | Crea/actualiza eventos en Google Calendar, nunca borra sin confirmación |
| `ai/` | Orquesta llamadas a Claude (research, outline, draft, quality check) |
| `writing_style/` | Reglas de estilo aplicadas a todo texto generado |
| `notifications/` | Envía notificaciones (Telegram inicialmente) |
| `review/` | Expone la pantalla de revisión y el estado de aprobación |
| `db/` | Persistencia de todo el estado |
| `scheduler/` | Orquesta el pipeline periódicamente (cron/worker) |

El pipeline corre como un worker periódico (ej. cada 1-2 horas) más triggers
manuales desde la UI ("sync now").

---

## 3. Estructura de carpetas propuesta

```
school-agent/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entrypoint
│   │   ├── core/
│   │   │   ├── config.py              # settings (env vars)
│   │   │   ├── security.py            # encryption, token handling
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/                # SQLAlchemy models (sección 4)
│   │   ├── schemas/                   # Pydantic schemas
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── courses.py
│   │   │       ├── assignments.py
│   │   │       ├── calendar.py
│   │   │       ├── review.py
│   │   │       └── notifications.py
│   │   ├── blackboard/
│   │   │   ├── auth.py
│   │   │   ├── browser.py
│   │   │   ├── courses.py
│   │   │   ├── assignments.py
│   │   │   ├── attachments.py
│   │   │   └── parser.py
│   │   ├── assignment_manager/
│   │   │   ├── priority.py
│   │   │   ├── checklist.py
│   │   │   └── work_plan.py
│   │   ├── calendar_sync/
│   │   │   └── google_calendar.py
│   │   ├── ai/
│   │   │   ├── client.py              # wrapper del Claude API
│   │   │   ├── research_agent.py
│   │   │   ├── draft_agent.py
│   │   │   ├── quality_check_agent.py
│   │   │   └── writing_style.py
│   │   ├── notifications/
│   │   │   └── telegram.py
│   │   └── scheduler/
│   │       └── pipeline.py
│   ├── tests/
│   │   ├── blackboard/
│   │   │   └── fixtures/              # HTML capturado, sin datos reales
│   │   ├── assignment_manager/
│   │   └── ai/
│   ├── alembic/                       # migraciones de DB
│   └── requirements.txt
├── frontend/
│   ├── app/                           # Next.js (App Router)
│   │   ├── dashboard/
│   │   └── review/[assignmentId]/
│   └── components/
├── docs/
│   └── (documentos de decisión adicionales, uno por módulo)
├── ARCHITECTURE.md
└── README.md
```

No se crea el código dentro de estas carpetas todavía — esto es la
estructura propuesta para aprobación.

---

## 4. Esquema de base de datos (PostgreSQL)

Entidades principales y relaciones clave:

```
User (1) ── (N) Course
Course (1) ── (N) Assignment
Assignment (1) ── (N) AssignmentAttachment
Assignment (1) ── (1) AssignmentStatus (estado actual, con historial aparte)
Assignment (1) ── (N) CalendarEvent
Assignment (1) ── (N) Research
Assignment (1) ── (N) Draft
Draft (1) ── (N) Citation
Assignment (1) ── (N) Notification
Assignment (1) ── (N) Review
```

Tablas:

**User**
`id, email, blackboard_username, timezone, created_at`
(la contraseña de Blackboard NUNCA se guarda aquí — ver sección 6)

**Course**
`id, user_id, blackboard_course_id, name, term, importance_weight, is_active`

**Assignment**
`id, course_id, blackboard_assignment_id, type (assignment|quiz|project|discussion),
title, description, instructions, due_date, timezone, points_possible,
rubric_json, url, status, priority, estimated_hours, created_at, last_seen_at,
last_modified_at`

**AssignmentAttachment**
`id, assignment_id, filename, url, mime_type, downloaded_path, checksum`

**AssignmentStatus** (historial de transiciones, tabla append-only)
`id, assignment_id, from_status, to_status, changed_by (system|user), changed_at, note`

Estados válidos:

```
DISCOVERED → PLANNED → IN_PROGRESS → DRAFT_READY → WAITING_FOR_REVIEW
→ APPROVED → SUBMITTED → ARCHIVED
```

Regla dura a nivel de aplicación (no solo UI): la transición
`DRAFT_READY → SUBMITTED` está **prohibida** en el código. Debe pasar por
`WAITING_FOR_REVIEW → APPROVED → SUBMITTED`, y el paso a `SUBMITTED` requiere
un flag explícito `approved_by_user_at IS NOT NULL` más una acción manual
separada (nunca automática, aunque exista integración de entrega en el futuro).

**CalendarEvent**
`id, assignment_id, google_event_id, calendar_id, synced_at, last_known_due_date`
(el `google_event_id` permite reconciliar sin duplicar ni pisar eventos ajenos)

**Research**
`id, assignment_id, source_type (web|book|ai), content, sources_json, created_at`

**Draft**
`id, assignment_id, version, content, status (draft|needs_personal_input|ready),
ai_generated_sections_json, created_at`

**Citation**
`id, draft_id, style (APA|MLA|Chicago), source_text, url, verified`

**Notification**
`id, assignment_id, channel (telegram|email), payload, sent_at, read_at`

**Review**
`id, assignment_id, reviewed_by, decision (approved|changes_requested),
comment, reviewed_at`

---

## 5. APIs propuestas (backend, FastAPI)

Todas bajo `/api/v1`, autenticadas (ver sección 6).

```
GET    /courses
GET    /courses/{id}/assignments

GET    /assignments?status=&priority=&due_within_days=
GET    /assignments/{id}                # detalle completo (instructions,
                                         # rubric, research, draft, checklist)
POST   /assignments/sync                # dispara el pipeline manualmente

GET    /assignments/{id}/research
GET    /assignments/{id}/draft
POST   /assignments/{id}/draft/regenerate

POST   /assignments/{id}/review/approve # marca APPROVED (nunca SUBMITTED)
POST   /assignments/{id}/review/request-changes

GET    /calendar/status
POST   /calendar/sync

GET    /notifications
POST   /notifications/{id}/read
```

No existe ningún endpoint `POST /assignments/{id}/submit` en esta fase.
Si en el futuro se decide construir integración de entrega real, seria un
módulo aparte, explícitamente aprobado, y seguiría requiriendo una acción
manual separada del botón de aprobación.

---

## 6. Modelo de seguridad

Credenciales de Blackboard:

- **Nunca se guarda la contraseña**, ni en texto plano ni cifrada.
- Si el login institucional usa SSO con MFA (lo más común: Okta, Azure AD,
  Shibboleth), Playwright abre una sesión **headful** una única vez para que
  el usuario complete login + MFA manualmente. El sistema nunca ve ni
  intercepta el código de MFA.
- Lo que se persiste es el **estado de sesión del navegador**
  (`storage_state` de Playwright: cookies + localStorage), cifrado en reposo
  con AES-256 (via `cryptography.Fernet`), con la clave de cifrado en un
  secret manager (o variable de entorno fuera del repo, mínimo viable).
  Cuando la sesión expira, el sistema notifica al usuario para repetir el
  login manual — nunca reintenta con credenciales guardadas.
- Si la institución expusiera una API oficial con OAuth2 (poco común para
  cuentas de estudiante, ver sección 7), se usaría el flujo OAuth estándar
  con refresh tokens cifrados, sin nunca tocar contraseñas.

Google Calendar:

- OAuth2 (flujo "installed app" / authorization code), scope mínimo
  necesario (`calendar.events`, no `calendar` completo).
- Refresh token cifrado en la base de datos.
- Eventos creados por el sistema se marcan con
  `extendedProperties.private.source = "student-academic-assistant"` para
  que la sincronización solo modifique/borre sus propios eventos, nunca
  eventos que el usuario creó manualmente.

Claude API:

- API key en variable de entorno / secret manager, nunca en el repo.

Manejo de casos límite:

- **Login fallido**: se reintenta un número limitado de veces y luego se
  notifica al usuario, no se hace retry infinito.
- **Blackboard caído**: el pipeline se salta ese ciclo y lo reporta, no
  marca assignments como eliminados.
- **Duplicados**: se deduplica por `blackboard_assignment_id`, no por título.
- **Due date cambiada**: se detecta el diff contra `last_modified_at` y se
  re-sincroniza el evento de calendar (update, no delete+create) y se
  notifica el cambio.
- **Assignment cancelado**: si desaparece de Blackboard, se marca
  `ARCHIVED` con nota, no se borra de la base de datos, y se pide
  confirmación antes de borrar el evento de Google Calendar.

---

## 7. Estrategia de integración con Blackboard

Comparación de opciones (sin asumir que ninguna API está disponible):

| Opción | Seguridad | Estabilidad | Mantenimiento | Auth/MFA | Riesgo de romperse | Viabilidad real para cuenta de estudiante |
|---|---|---|---|---|---|---|
| **Blackboard REST API (Anthology)** | Alta (OAuth2) | Alta | Baja | OAuth2, gestionado por la institución | Bajo | **Normalmente NO viable**: requiere que la institución registre una aplicación en su Developer Portal y otorgue credenciales `client_id`/`client_secret` a nivel de integración, algo que un estudiante individual casi nunca puede autoconfigurar |
| **Blackboard Ultra APIs / LTI** | Alta | Alta | Baja | Depende de LTI 1.3 + institución | Bajo | Pensada para integraciones de terceros aprobadas por la institución, no para un usuario individual |
| **Browser automation (Playwright)** | Media (depende de cómo se guarde la sesión) | Media (sensible a cambios de UI) | Media-Alta | Compatible con SSO/MFA manual (login headful) | Medio-Alto | **Viable siempre**, funciona con cualquier cuenta que pueda iniciar sesión por navegador |
| **Chrome extension** | Media | Media | Alta (dos codebases) | Reutiliza sesión ya logueada | Medio | Viable pero no aporta ventaja real sobre Playwright con `storage_state` persistido; añade complejidad de distribución/instalación |
| **Scraping de emails de notificación de Blackboard** | Alta | Baja (datos incompletos) | Media | N/A | Alto (falta info como rubric, adjuntos) | Complementario, no sustituto |

**Recomendación**: usar la API oficial *solo si* se confirma que existe
acceso (ver checklist abajo). Si no, usar **Playwright de forma modular y
resiliente**, exactamente como pide el requerimiento: preferir API oficial
sobre browser automation, y si no es viable, Playwright.

Diseño del módulo Playwright (`blackboard/`):

- `auth.py`: maneja login (incluye pausa para MFA manual la primera vez),
  guarda/restaura `storage_state` cifrado, detecta sesión expirada.
- `browser.py`: wrapper de Playwright (contexto, reintentos, timeouts
  configurables, screenshots en caso de error para debugging).
- `courses.py`: navega el listado de cursos.
- `assignments.py`: navega assignments/quizzes/projects/discussions por curso.
- `attachments.py`: descarga adjuntos (read-only, sin tocar submissions).
- `parser.py`: convierte HTML a los objetos normalizados (sección de datos
  más abajo), aislado del resto para poder testear con fixtures de HTML
  guardado, sin necesidad de una sesión real.

Resiliencia: `parser.py` usa selectores con fallback (varios selectores
candidatos por campo) y logging explícito cuando un selector deja de
funcionar, en vez de fallar en silencio. Cada corrida guarda snapshot de
errores para poder ajustar selectores rápido cuando Blackboard cambie su UI.

El scraper es **estrictamente read-only**: nunca hace click en botones de
submit, nunca modifica campos, nunca toca configuración de curso.

**Información que necesito de ti antes de implementar este módulo** (para no
inventar nada):

1. URL base de tu Blackboard (ej. `https://universidad.blackboard.com`).
2. Si es Blackboard Learn **Ultra** o **Original Experience** (se ve
   distinto en la navegación de cursos).
3. Si tu universidad tiene un portal de desarrollador de
   Blackboard/Anthology y si tu cuenta (o alguna cuenta institucional a la
   que tengas acceso) tiene client credentials — si no lo sabes, lo más
   probable es que no, y vamos directo a Playwright.
4. Cómo inicias sesión: usuario/contraseña directo, o SSO (Okta/Azure
   AD/Shibboleth/otro) con MFA.
5. Si es posible, capturas de pantalla (sin datos sensibles) de la vista de
   cursos y de un assignment, para diseñar los selectores del parser sin
   adivinar la estructura del HTML.

---

## 8. Integración con Google Calendar

- Google Calendar API v3, OAuth2 con scope `calendar.events`.
- Un evento por assignment con: título (`{course} — {assignment}`),
  descripción (due date, prioridad, tiempo estimado, link a Blackboard),
  fecha de entrega como fin del evento, y un bloque de tiempo estimado antes
  del due date como el evento en sí (o un evento "trabajo" separado del
  evento "deadline" — a decidir en la fase de implementación).
- Reconciliación por `google_event_id` guardado en `CalendarEvent`: si el
  assignment ya tiene evento, se actualiza; si no, se crea. Nunca se crea
  un evento duplicado.
- **Nunca se borra ni modifica un evento que el sistema no creó.** Antes de
  borrar un evento propio (ej. assignment cancelado), se pide confirmación
  explícita al usuario.
- Cambios de due date detectados en Blackboard actualizan el evento
  existente (no delete+create, para no perder invitados/recordatorios
  configurados manualmente por el usuario en ese evento).

---

## 9. Orquestación de la capa de IA (Claude)

Agentes especializados, cada uno con un system prompt acotado a su tarea:

- **AssignmentManagerAgent**: convierte instrucciones crudas en resumen,
  checklist y plan de trabajo. No investiga ni redacta.
- **ResearchAgent**: busca/organiza fuentes relevantes cuando el assignment
  lo requiere. Marca explícitamente qué es información verificable vs. qué
  necesita que el estudiante la revise.
- **DraftAgent**: prepara outline y draft siguiendo las reglas de estilo de
  escritura (abajo). Nunca inventa opinión personal ni experiencia del
  estudiante: usa marcadores `[PERSONAL OPINION NEEDED]`,
  `[ADD YOUR EXPERIENCE]`, `[ADD YOUR EXAMPLE]` cuando corresponda.
- **QualityCheckAgent**: compara el draft contra la rubric, señala
  requisitos faltantes, verifica formato de citas, y le pide al usuario
  aclarar puntos ambiguos antes de marcar `DRAFT_READY`.

Reglas de estilo de escritura (aplican a Research/Draft/QualityCheck):

- Nivel: estudiante universitario de tercer semestre aproximadamente.
- Natural, directo, claro, vocabulario normal, no exageradamente formal.
- Evitar muletillas típicas de texto generado por IA ("Furthermore",
  "Moreover", "It is important to note that", "Delve into", "Robust",
  "Comprehensive", conclusiones exageradas, introducciones genéricas,
  párrafos con estructura repetitiva, uso excesivo de guiones largos "—".
- **No** se intenta evadir detectores de IA ni se insertan errores
  artificiales. La prioridad es que el texto sea claro y natural, no que
  parezca "menos IA" por trucos.
- Todo draft se entrega marcado como borrador para revisión personal, nunca
  como producto final.

Checkpoint duro entre capas: el `QualityCheckAgent` es el único que puede
mover un assignment a `DRAFT_READY`, y **ningún agente de IA puede mover un
assignment a `APPROVED` o `SUBMITTED`** — esas transiciones están fuera del
alcance de lo que el código de IA puede tocar, solo la acción humana en la
UI de revisión las dispara.

---

## 10. Estrategia de testing

- **Backend (pytest)**: máquina de estados de `AssignmentStatus` (incluye
  test explícito de que `DRAFT_READY → SUBMITTED` directo lanza error),
  cálculo de prioridad (casos borde de fechas/puntos/dificultad), lógica de
  reconciliación de Google Calendar (no duplica, no borra eventos ajenos).
- **Blackboard parser**: tests contra fixtures de HTML guardado (capturado
  una vez, sin credenciales ni datos sensibles en el repo), cubriendo
  extracción de assignments, fechas, duplicados, HTML malformado, y
  detección de sesión expirada — sin depender de una sesión real de
  Blackboard en CI.
- **AI layer**: tests de contrato (formato de salida esperado, presencia de
  marcadores `[PERSONAL OPINION NEEDED]` cuando corresponde) más revisión
  manual periódica de calidad de estilo, ya que la calidad de redacción no
  se puede validar 100% de forma automática.
- **E2E manual**: checklist para correr el pipeline completo contra tu
  Blackboard real una vez el módulo esté implementado, documentado paso a
  paso antes de entregarte el módulo de Blackboard (como pediste en el
  prompt de ese módulo).

---

## Siguiente paso

Este documento es la propuesta completa de Fase 1. Falta tu aprobación para
empezar a construir, y para el módulo de Blackboard específicamente falta la
información listada en la sección 7. Una vez confirmes ambas cosas,
seguimos con la implementación módulo por módulo, empezando por
`blackboard/`.
