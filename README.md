# Student Academic Assistant

Sistema para administrar automáticamente cursos universitarios en Blackboard,
detectar assignments próximos a vencer, sincronizarlos con Google Calendar,
y preparar material de apoyo (research, outlines, drafts) con revisión humana
obligatoria antes de cualquier entrega.

## Estado del proyecto: Fase 1.5 — Arquitectura revisada y endurecida

Este repositorio está en la etapa de **análisis y diseño**. Todavía no hay
código de producción. `ARCHITECTURE.md` pasó por una revisión técnica tipo
Senior Staff Engineer que, entre otras cosas, agrega enforcement técnico
(código + trigger de base de datos + roles de mínimo privilegio) para que
la regla de aprobación humana no dependa solo de un prompt de Claude:

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

Este documento de arquitectura requiere tu aprobación antes de empezar a
construir. Además, para implementar el módulo de Blackboard necesito que
confirmes (ver sección 7 de `ARCHITECTURE.md`):

- URL base de tu Blackboard institucional (ej. `https://xxx.blackboard.com`).
- Si tu institución usa **Blackboard Learn Ultra** o el **Original Experience**.
- Si tu institución tiene un portal de desarrolladores de Blackboard/Anthology
  con acceso a REST API para tu cuenta (la mayoría de cuentas de estudiante
  no lo tienen; si no lo tienes, usaremos automatización con Playwright).
- Cómo inicias sesión hoy: usuario/contraseña directo en Blackboard, o SSO
  institucional (Okta, Azure AD, Shibboleth, etc.) con MFA.

Una vez apruebes esta revisión (Fase 1.5) y confirmes estos puntos,
construiremos el sistema módulo por módulo, empezando por
`BlackboardProvider` (`PlaywrightBlackboardProvider`).
