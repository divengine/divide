# divide: technical documentation

This folder holds the technical documentation of divide, the environment for
deterministic code generation with the Divengine libraries, organised as the
artifacts of the **Rational Unified Process** (RUP). The user manual lives in
the [wiki](https://github.com/divengine/divide/wiki) and is also built into
divide's help (F1). Div's own language reference lives with
[Div](https://github.com/divengine/div/tree/master/docs). These documents
describe how divide is built and why, and they link to those other sources
instead of repeating them.

## How RUP is applied

RUP organises a project along two axes: **phases** in time (Inception,
Elaboration, Construction, Transition), each made of iterations, and
**disciplines** (Business Modeling, Requirements, Analysis & Design,
Implementation, Test, Deployment, plus the supporting Configuration & Change
Management, Project Management and Environment). Each discipline produces
artifacts. divide is a small, single-team project, so this is a *tailored*
development case: one document per artifact that carries weight, kept next to
the code and updated in the same commits as the changes it describes.

| Discipline | Artifact | Document |
|---|---|---|
| Requirements | Vision | [vision.md](vision.md) |
| Requirements | Glossary | [glossary.md](glossary.md) |
| Requirements | Use-Case Model (actors, use cases, specifications) | [use-case-model.md](use-case-model.md) |
| Requirements | Supplementary Specification (non-functional requirements, constraints) | [supplementary-specification.md](supplementary-specification.md) |
| Analysis & Design | Software Architecture Document (4+1 views) | [software-architecture.md](software-architecture.md) |
| Analysis & Design | Design Model (subsystems, classes, collaborations) | [design-model.md](design-model.md) |
| Analysis & Design | Div as seen by the editor (design note on the lexer) | [div-language.md](div-language.md) |
| Test | Test Plan | [test-plan.md](test-plan.md) |
| Deployment | Deployment and configuration | [deployment.md](deployment.md) |
| Project Management | Iteration Plan and history, Risk List | [iteration-plan.md](iteration-plan.md) |
| Configuration & Change Mgmt | Development case (workflow, conventions) | [development-case.md](development-case.md) |

## Reading order

- **New to divide:** start with the Vision, then the use-case model.
- **Changing the code:** read the Software Architecture Document, then the part of the Design Model you need, then the development case.
- **Reviewing quality:** read the supplementary specification and the test plan.

## Keeping it current

A change that alters behaviour updates the use case it touches. A change that
adds a module or crosses a layer updates the architecture and design
documents. A new iteration gets a row in the iteration plan. The documents
name modules and classes, not line numbers, so they do not go stale with
every edit.
