# Tanzu PostgreSQL Ansible

This project contains Ansible playbooks for installing and configuring PostgreSQL 18.3 on Rocky Linux 9, including enabling the PostGIS and pgvector extensions, as well as installing the required client tools on other nodes.

## Project Structure

The project is structured inside the `ansible/` directory:

```text
ansible/
├── .vault_pass           # Executable script to read the vault password
├── .vault_pass_txt       # Plain text file with the vault password (DO NOT COMMIT TO GIT)
├── ansible.cfg           # Project-specific Ansible configuration
├── site.yml              # Main playbook that imports the playbooks below
├── playbooks/            # Directory containing individual playbooks
│   ├── install_server.yml
│   └── install_clients.yml
└── inventory/
    ├── hosts.yml         # Inventory file containing servers and clients
    └── group_vars/
        └── all/
            └── vault.yml # Encrypted variables (e.g., passwords)
```

## Prerequisites

- Ansible installed on the control machine.
- SSH access to the target machines (`10.85.10.241`, `10.85.10.238`).
- Sudo privileges on the target machines.

## Initial Setup

### 1. Export the ANSIBLE_CONFIG variable

To ensure that Ansible uses the configuration specific to this project (defined in `ansible/ansible.cfg`), you must export the `ANSIBLE_CONFIG` environment variable pointing to this file.

From the root of the repository, run:

```bash
export ANSIBLE_CONFIG="$(pwd)/ansible/ansible.cfg"
```

*Note: You can add this line to your `~/.bashrc` or `~/.zshrc` if you work frequently on this project.*

### 2. Ansible Vault Configuration and Encryption

Passwords and sensitive data are stored in `ansible/inventory/group_vars/all/vault.yml`. For enhanced security, this file must be encrypted.

Follow these steps to encrypt it for the first time:

1. Ensure your master password is saved in the `ansible/.vault_pass_txt` file.
2. Grant execution permissions to the reader script if it doesn't have them:
   ```bash
   chmod +x ansible/.vault_pass
   ```
3. Add your `localhost` sudo password to the vault so Ansible doesn't prompt you when installing packages locally. Edit `ansible/inventory/group_vars/all/vault.yml` and add:
   ```yaml
   localhost_sudo_pass: "YOUR_LOCAL_SUDO_PASSWORD"
   ```
4. Encrypt the `vault.yml` file using the `ansible-vault` tool:
   ```bash
   cd ansible
   ansible-vault encrypt inventory/group_vars/all/vault.yml
   ```

If you need to edit the file later, you can use:

```bash
ansible-vault edit inventory/group_vars/all/vault.yml
```

> **IMPORTANT!** Never commit the `ansible/.vault_pass_txt` file to your version control repository.

## Running the Playbooks

Once the `ANSIBLE_CONFIG` variable is configured and `vault.yml` is encrypted, you can run the main playbook (`site.yml`) to install PostgreSQL and its clients.

From the `ansible/` folder, you can run the whole project:

```bash
cd ansible
ansible-playbook site.yml
```

### Running Specific Tags

The `site.yml` playbook imports the specific playbooks and assigns tags to them, allowing you to run them independently.

**To run only the PostgreSQL Server installation:**

```bash
ansible-playbook site.yml --tags "server"
```

**To run only the PostgreSQL Clients installation:**

```bash
ansible-playbook site.yml --tags "clients"
```