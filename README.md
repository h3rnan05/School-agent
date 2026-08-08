# Student Academic Assistant

Sistema para administrar automáticamente cursos universitarios en Blackboard,
detectar assignments próximos a vencer, sincronizarlos con Google Calendar,
y preparar material de apoyo (research, outlines, drafts) con revisión humana
obligatoria antes de cualquier entrega.

## Estado del proyecto: Fase 1 — Propuesta de arquitectura

Este repositorio está en la etapa de **análisis y diseño**. Antes de escribir
código de producción, se documentó en [`ARCHITECTURE.md`](./ARCHITECTURE.md):

1. Análisis de requerimientos
2. Arquitectura propuesta
3. Estructura de carpetas
4. Esquema de base de datos
5. APIs propuestas
6. Modelo de seguridad
7. Estrategia de integración con Blackboard (sin inventar endpoints)
8. Integración con Google Calendar
9. Orquestación de la capa de IA (Claude)
10. Estrategia de testing

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

Una vez apruebes la arquitectura y confirmes estos puntos, construiremos el
sistema módulo por módulo, empezando por el módulo de Blackboard.
