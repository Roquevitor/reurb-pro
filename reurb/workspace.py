"""Foundation for REURB Pro organizations, teams and work management.

This migration deliberately creates one legacy workspace and assigns all existing
records to it. It does NOT enable multi-tenant access yet: application routes must
be scoped and authorization-tested before additional organizations are provisioned.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


LEGACY_ORG_NAME = "Organização principal"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_org_column(conn: sqlite3.Connection, table: str, organization_id: int) -> None:
    if "organization_id" not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN organization_id INTEGER")
    conn.execute(
        f"UPDATE {table} SET organization_id=? WHERE organization_id IS NULL",
        (organization_id,),
    )


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create workspace tables and safely attach pre-existing data to org #1."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        );

        CREATE TABLE IF NOT EXISTS memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN
                ('owner','engineer','field_technician','surveyor','registral_assistant','reviewer')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE(organization_id,user_id),
            FOREIGN KEY(organization_id) REFERENCES organizations(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY(organization_id) REFERENCES organizations(id)
        );

        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            created_at TEXT NOT NULL,
            PRIMARY KEY(team_id,user_id),
            FOREIGN KEY(team_id) REFERENCES teams(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS project_members (
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'collaborator',
            created_at TEXT NOT NULL,
            PRIMARY KEY(project_id,user_id),
            FOREIGN KEY(project_id) REFERENCES projetos(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            team_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'todo'
                CHECK(status IN ('todo','in_progress','review','done','blocked')),
            priority TEXT NOT NULL DEFAULT 'normal'
                CHECK(priority IN ('low','normal','high','urgent')),
            assigned_user_id INTEGER,
            created_by_user_id INTEGER,
            due_date TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(organization_id) REFERENCES organizations(id),
            FOREIGN KEY(project_id) REFERENCES projetos(id),
            FOREIGN KEY(team_id) REFERENCES teams(id),
            FOREIGN KEY(assigned_user_id) REFERENCES users(id),
            FOREIGN KEY(created_by_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS activity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            project_id INTEGER,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(organization_id) REFERENCES organizations(id),
            FOREIGN KEY(project_id) REFERENCES projetos(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_memberships_user
            ON memberships(user_id, is_active);
        CREATE INDEX IF NOT EXISTS idx_teams_org
            ON teams(organization_id, is_active);
        CREATE INDEX IF NOT EXISTS idx_tasks_org_project
            ON tasks(organization_id, project_id, status);
        CREATE INDEX IF NOT EXISTS idx_tasks_assignee
            ON tasks(assigned_user_id, status, due_date);
        CREATE INDEX IF NOT EXISTS idx_activity_org_date
            ON activity_events(organization_id, created_at);
        """
    )

    conn.execute(
        """INSERT OR IGNORE INTO organizations(name,slug,status,created_at)
           VALUES(?,?,?,?)""",
        (LEGACY_ORG_NAME, "organizacao-principal", "active", now),
    )

    organization_id = conn.execute(
        "SELECT id FROM organizations WHERE slug='organizacao-principal'"
    ).fetchone()[0]

    # Existing installations are migrated in place. Their records are not copied
    # or deleted; all legacy records belong to the first workspace.
    tenant_tables = (
        "projetos", "vertices", "pessoas", "prefeituras", "cartorios",
        "bairros", "logradouros", "cadastro_pessoas", "nucleos",
        "prefeitura_cartorios", "historico_logradouros", "auditoria",
    )
    for table in tenant_tables:
        _add_org_column(conn, table, organization_id)
        # Legacy route handlers do not yet pass organization_id. The trigger
        # keeps newly inserted rows in the legacy workspace during transition.
        conn.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_default_org
                AFTER INSERT ON {table}
                WHEN NEW.organization_id IS NULL
                BEGIN
                    UPDATE {table} SET organization_id={organization_id}
                    WHERE rowid=NEW.rowid;
                END"""
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projetos_organization "
        "ON projetos(organization_id, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pessoas_organization "
        "ON pessoas(organization_id, proj_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vertices_organization "
        "ON vertices(organization_id, proj_id)"
    )
    conn.commit()
