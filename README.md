# acampo.saas_cac

Ansible collection for **Configuration as Code (CaC)** of the SaaS platform. It holds playbooks, roles, and plugins used to declare, apply, and reconcile desired configuration across SaaS environments in a repeatable, version-controlled way.

## Purpose

This collection automates SaaS CaC workflows: defining configuration in Git, applying it with Ansible, and keeping runtime state aligned with the declared source of truth. Use it alongside your broader automation stack (for example, source-of-truth and controller collections) rather than as a one-off set of ad hoc playbooks.

## Requirements

- Ansible Core 2.14+ (adjust in `meta/runtime.yml` when you set a minimum version)
- Access to target hosts or APIs your roles and modules will manage
- Any collection dependencies listed in `galaxy.yml` under `dependencies`

## Installation

Install from the collection path or build and publish to Ansible Galaxy / Private Automation Hub.

**Local development (collection root):**

```bash
ansible-galaxy collection install . --force
```

**From a requirements file:**

```yaml
# requirements.yml
collections:
  - name: acampo.saas_cac
    version: ">=1.0.0"
```

```bash
ansible-galaxy collection install -r requirements.yml
```

## Usage

Reference roles and content by their fully qualified collection name (FQCN):

```yaml
- name: Apply SaaS CaC configuration
  hosts: localhost
  gather_facts: false
  roles:
    - role: acampo.saas_cac.<role_name>
```

Playbooks shipped in the collection can be run directly:

```bash
ansible-playbook acampo.saas_cac.<playbook_name>
```

Replace `<role_name>` and `<playbook_name>` with roles and playbooks as you add them under `roles/` and `playbooks/`.

## Collection layout

| Path | Description |
|------|-------------|
| `roles/` | Reusable configuration roles (tenants, services, policies, etc.) |
| `playbooks/` | Entry-point playbooks for apply, validate, or drift checks |
| `plugins/` | Custom modules, lookups, filters, and module utilities |
| `meta/runtime.yml` | Collection metadata and plugin routing |

## Development

Build an installable artifact from the collection root:

```bash
ansible-galaxy collection build
ansible-galaxy collection install acampo-saas_cac-*.tar.gz --force
```

Run sanity tests when you add content:

```bash
ansible-test sanity --docker
```

## Versioning

Collection version follows [Semantic Versioning](https://semver.org/) and is defined in `galaxy.yml`.

## License

GPL-2.0-or-later (see `galaxy.yml`).
