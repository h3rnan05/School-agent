# Student Academic Assistant

Sistema para administrar automáticamente cursos universitarios en Blackboard,
detectar assignments próximos a vencer, sincronizarlos con Google Calendar,
y preparar material de apoyo (research, outlines, drafts) con revisión humana
obligatoria antes de cualquier entrega.

## Estado del proyecto: Fase 3 — Notificador + bot de Telegram, sobre Blackboard real (UDEM)

Arquitectura (Fase 1.5) **aprobada**. Módulo de Blackboard (Fase 2/2.1)
construido y validado contra UDEM (`cursos-udem.blackboard.com`, Ultra
Experience, cursos individuales en Original Course View):
[`backend/`](./backend) contiene `BlackboardProvider` /
`PlaywrightBlackboardProvider`, con parsers separados por tipo de curso
(`CourseListParser`, `OriginalCourseParser`, `UltraCourseParser`,
`AssignmentParser`) — acceso **solo lectura**, sin guardar tu contraseña
nunca. Sobre eso, Fase 3 agrega `app/notifier/` (avisa por Telegram cuando
hay una tarea nueva o cambia una fecha) y `app/telegram_bot/` (comandos
`/tareas`, `/proxima`, `/resumen` + chat libre con Claude sobre una tarea
elegida) — ambos corren localmente en tu Mac vía `launchd`, nunca en un
servidor en la nube, y siguen siendo estrictamente de solo lectura hacia
Blackboard. Ver [`backend/README.md`](./backend/README.md), sección "Phase
3 — Telegram bot", para el setup completo.

**Importante**: el login interactivo (`blackboard login`) no se puede
ejecutar dentro de una sesión de Claude Code en la nube — no hay pantalla
ni terminal interactiva de tu lado ahí. Tenés que correrlo en tu propia
máquina; ver [`backend/README.md`](./backend/README.md), sección "this
must be run on YOUR machine", para el detalle y los siguientes pasos.

Deliberadamente fuera de esta fase (según lo pedido): PostgreSQL, Google
Calendar, frontend, y cualquier tipo de submission — el bot solo lee y
conversa, nunca sube ni completa nada en Blackboard.

`ARCHITECTURE.md` sigue siendo la referencia completa del sistema. Pasó por
una revisión técnica tipo Senior Staff Engineer que, entre otras cosas,
agrega enforcement técnico (código + trigger de base de datos + roles de
mínimo privilegio) para que la regla de aprobación humana no dependa solo
de un prompt de Claude:

1. Análisis de requerimientos
2. Arquitectura propuesta
3. Estructura de carpetas
4. **Máquina de estados con "hard stop" técnico** (3 capas independientes)
5. Esquema de base de datos (incluye `AgentRun`, `AuditLog`, `AssignmentChangeLog`, `Source`)
6. APIs propuestas
7. **Matriz de permisos por agente (mínimo privilegio)** — ningún agente de IA escribe `status`
8. Integración con Blackboard vía abstracción `BlackboardProvider`
9. Integración con Google Calendar (timezone, reconciliación, cancelaciones)
10. Alcance del Student Writing Style Agent (solo `Draft.content`)
11. Modelo de seguridad / threat model
12. Observability (WHO/WHAT/WHEN/WHY/INPUT/OUTPUT/RESULT/ERROR)
13. Failure recovery
14. Human-in-the-loop UX
15. Estrategia de testing

## Principio no negociable

```
DISCOVERY → PLANNING → PREPARATION → REVIEW → USER APPROVAL
```

Nunca:

```
DISCOVERY → AUTOMATIC SUBMISSION
```

El sistema **nunca** envía un assignment automáticamente. La última acción
del flujo siempre requiere aprobación humana explícita.

## Próximos pasos

1. En tu máquina: `git pull`, después seguí "Phase 3 — Telegram bot" en
   `backend/README.md` para correr `python -m app.notifier run-once` y
   `python -m app.telegram_bot run` manualmente primero.
2. Confirmá que `/start`, `/tareas`, `/proxima` y `/resumen <n>` responden
   bien en Telegram, y que una vez que aparezca una tarea real con fecha
   de entrega el notificador te avisa.
3. Si eso funciona, instalá los `launchd` agents (también documentado ahí)
   para que corra solo, sin que tengas que dejar una terminal abierta.
4. No avanzo a la siguiente fase (Google Calendar, submission asistido)
   hasta que confirmes que esto funciona de punta a punta contra tu
   Blackboard real.
