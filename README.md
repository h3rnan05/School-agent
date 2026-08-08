# Student Academic Assistant

Sistema para administrar automáticamente cursos universitarios en Blackboard,
detectar assignments próximos a vencer, sincronizarlos con Google Calendar,
y preparar material de apoyo (research, outlines, drafts) con revisión humana
obligatoria antes de cualquier entrega.

## Estado del proyecto: Fase 2 — Módulo de Blackboard implementado

Arquitectura (Fase 1.5) **aprobada**. Primer módulo de código real
construido y probado: [`backend/`](./backend) contiene `BlackboardProvider`
con su implementación `PlaywrightBlackboardProvider` — acceso **solo
lectura** a Blackboard, sin guardar tu contraseña nunca. Ver
[`backend/README.md`](./backend/README.md) para cómo instalarlo y correr
`blackboard login / courses / assignments / upcoming`.

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

La Fase 2 (módulo de Blackboard) queda entregada para que la pruebes contra
tu Blackboard real siguiendo `backend/README.md`. Es muy probable que el
parser (`backend/app/blackboard/parser.py`) necesite ajustes de selectores
una vez lo corras de verdad — se escribió sin acceso a HTML real de tu
Blackboard, de forma honesta y documentada (ver `ARCHITECTURE.md` sección
16 y el aviso en `backend/README.md`).

No se avanza a la siguiente fase (Google Calendar, IA, notificaciones,
frontend) hasta que confirmes que `login`, `courses`, `assignments` y
`upcoming` funcionan correctamente contra tu Blackboard.
