# Student Academic Assistant

Sistema para administrar automáticamente cursos universitarios en Blackboard,
detectar assignments próximos a vencer, sincronizarlos con Google Calendar,
y preparar material de apoyo (research, outlines, drafts) con revisión humana
obligatoria antes de cualquier entrega.

## Estado del proyecto: Fase 2.1 — Validación contra Blackboard real (UDEM), pendiente de correr localmente

Arquitectura (Fase 1.5) **aprobada**. Módulo de Blackboard construido y
extendido con los datos reales de UDEM (`cursos-udem.blackboard.com`,
Ultra Experience, cursos individuales en Original Course View):
[`backend/`](./backend) contiene `BlackboardProvider` /
`PlaywrightBlackboardProvider`, con parsers separados por tipo de curso
(`CourseListParser`, `OriginalCourseParser`, `UltraCourseParser`,
`AssignmentParser`) — acceso **solo lectura**, sin guardar tu contraseña
nunca.

**Importante**: el login interactivo (`blackboard login`) no se puede
ejecutar dentro de una sesión de Claude Code en la nube — no hay pantalla
ni terminal interactiva de tu lado ahí. Tenés que correrlo en tu propia
máquina; ver [`backend/README.md`](./backend/README.md), sección "this
must be run on YOUR machine", para el detalle y los siguientes pasos.

Deliberadamente fuera de esta fase (según lo pedido): PostgreSQL, Google
Calendar, Claude/IA, Telegram, frontend, y cualquier tipo de submission.

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

1. Corré `blackboard login / courses / assignments / upcoming` en tu
   máquina (no en esta sesión) siguiendo `backend/README.md`.
2. Si `courses` o `assignments` viene vacío o con datos incorrectos, es
   casi seguro un tema de selectores — pasame lo que pide
   `backend/app/blackboard/parsers/DOM_NOTES.md` (HTML de una sola tarjeta
   de curso, sin necesidad de compartir tu sesión ni contraseña) y lo
   ajusto con evidencia real en vez de adivinar de nuevo.
3. No avanzo a la siguiente fase (Google Calendar, IA, notificaciones,
   frontend) hasta que confirmes que el pipeline completo funciona contra
   tu Blackboard real.
