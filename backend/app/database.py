import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "backend" / "data"
DB_PATH = DATA_DIR / "cambridge_cofounder.db"
UPLOADS_DIR = ROOT_DIR / "backend" / "uploads"

OTP_TTL_MINUTES = 10
SESSION_TTL_DAYS = 7

SKILLS = {"Engineering", "Product", "Business"}
COMMITMENT_LEVELS = {"Exploring", "Part-time", "Serious"}
LOOKING_FOR_OPTIONS = {"Technical", "Non-technical", "Either"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing_columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing_columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                college TEXT NOT NULL,
                course TEXT NOT NULL,
                year INTEGER NOT NULL,
                what_have_you_built TEXT NOT NULL,
                skills_json TEXT NOT NULL,
                commitment_level TEXT NOT NULL,
                looking_for TEXT NOT NULL,
                linkedin_url TEXT,
                cam_email TEXT NOT NULL,
                profile_photo_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS connect_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_user_id INTEGER NOT NULL,
                recipient_user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                responded_at TEXT,
                FOREIGN KEY (sender_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (recipient_user_id) REFERENCES users(id) ON DELETE CASCADE,
                CHECK (status IN ('pending', 'accepted', 'declined')),
                UNIQUE (sender_user_id, recipient_user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                usage_date TEXT NOT NULL,
                action_type TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE (user_id, usage_date, action_type)
            );
            """
        )
        ensure_column(conn, "profiles", "profile_photo_path", "TEXT")
        conn.commit()


def avatar_url_for_profile(user_id: int, first_name: str, last_name: str, profile_photo_path: str | None) -> str:
    if profile_photo_path:
        return f"/uploads/{profile_photo_path}"
    initials = f"{(first_name[:1] or '').upper()}{(last_name[:1] or '').upper()}"
    return f"/api/avatars/default/{user_id}?initials={initials or 'C'}"


def row_to_profile(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    profile_photo_path = row["profile_photo_path"] if "profile_photo_path" in row.keys() else None
    return {
        "user_id": row["user_id"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "college": row["college"],
        "course": row["course"],
        "year": row["year"],
        "what_have_you_built": row["what_have_you_built"],
        "skills": json.loads(row["skills_json"]),
        "commitment_level": row["commitment_level"],
        "looking_for": row["looking_for"],
        "linkedin_url": row["linkedin_url"],
        "cam_email": row["cam_email"],
        "profile_photo_path": profile_photo_path,
        "avatar_url": avatar_url_for_profile(row["user_id"], row["first_name"], row["last_name"], profile_photo_path),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def validate_email(email: str, allow_demo: bool = False) -> str:
    normalized = email.strip().lower()
    if allow_demo and normalized == "demo@cambridgecofounder.local":
        return normalized
    if not normalized.endswith("@cam.ac.uk"):
        raise ValueError("Email must end with @cam.ac.uk")
    return normalized


def validate_profile_payload(payload: dict[str, Any], user_email: str) -> dict[str, Any]:
    cleaned = {
        "first_name": str(payload.get("first_name", "")).strip(),
        "last_name": str(payload.get("last_name", "")).strip(),
        "college": str(payload.get("college", "")).strip(),
        "course": str(payload.get("course", "")).strip(),
        "year": int(payload.get("year", 0)),
        "what_have_you_built": str(payload.get("what_have_you_built", "")).strip(),
        "skills": payload.get("skills") or [],
        "commitment_level": str(payload.get("commitment_level", "")).strip(),
        "looking_for": str(payload.get("looking_for", "")).strip(),
        "linkedin_url": str(payload.get("linkedin_url", "")).strip(),
        "cam_email": str(payload.get("cam_email", "")).strip() or user_email,
    }

    required_text_fields = [
        "first_name",
        "last_name",
        "college",
        "course",
        "what_have_you_built",
        "commitment_level",
        "looking_for",
    ]
    for field in required_text_fields:
        if not cleaned[field]:
            raise ValueError(f"{field.replace('_', ' ').title()} is required")

    if cleaned["year"] < 1 or cleaned["year"] > 10:
        raise ValueError("Year must be between 1 and 10")

    if len(cleaned["what_have_you_built"]) < 12:
        raise ValueError("What have you built must be at least 12 characters")
    if len(cleaned["what_have_you_built"]) > 300:
        raise ValueError("What have you built must be 300 characters or fewer")

    if not isinstance(cleaned["skills"], list):
        raise ValueError("Skills must be a list")
    cleaned["skills"] = [str(skill).strip() for skill in cleaned["skills"] if str(skill).strip()]
    if not cleaned["skills"]:
        raise ValueError("Select at least one skill")
    if len(cleaned["skills"]) > 2:
        raise ValueError("Select at most two skills")
    if any(skill not in SKILLS for skill in cleaned["skills"]):
        raise ValueError("Skills must be chosen from Engineering, Product, or Business")

    if cleaned["commitment_level"] not in COMMITMENT_LEVELS:
        raise ValueError("Invalid commitment level")

    if cleaned["looking_for"] not in LOOKING_FOR_OPTIONS:
        raise ValueError("Invalid looking for option")

    cleaned["cam_email"] = validate_email(cleaned["cam_email"])

    if cleaned["linkedin_url"] and not (
        cleaned["linkedin_url"].startswith("https://linkedin.com/")
        or cleaned["linkedin_url"].startswith("https://www.linkedin.com/")
    ):
        raise ValueError("LinkedIn URL must start with https://linkedin.com/ or https://www.linkedin.com/")

    return cleaned


def create_otp(email: str) -> str:
    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = (now_utc() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO otp_codes (email, code, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (email, code, expires_at, now_iso()),
        )
        conn.commit()
    return code


def consume_otp(email: str, code: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, expires_at
            FROM otp_codes
            WHERE email = ? AND code = ? AND consumed_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (email, code),
        ).fetchone()
        if not row:
            return False
        expires_at = parse_iso(row["expires_at"])
        if not expires_at or expires_at < now_utc():
            return False
        conn.execute(
            "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
            (now_iso(), row["id"]),
        )
        conn.commit()
    return True


def get_or_create_user(email: str, is_demo: bool = False) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            return dict(row)
        cursor = conn.execute(
            "INSERT INTO users (email, is_demo, created_at) VALUES (?, ?, ?)",
            (email, 1 if is_demo else 0, now_iso()),
        )
        conn.commit()
        created = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(created)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (now_utc() + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (user_id, token, expires_at, now_iso()),
        )
        conn.commit()
    return token


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def get_user_by_token(token: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, now_iso()),
        ).fetchone()
        return dict(row) if row else None


def get_profile(user_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        return row_to_profile(row)


def upsert_profile(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        serialized_skills = json.dumps(payload["skills"])
        timestamp = now_iso()
        if existing:
            conn.execute(
                """
                UPDATE profiles
                SET first_name = ?, last_name = ?, college = ?, course = ?, year = ?,
                    what_have_you_built = ?, skills_json = ?, commitment_level = ?,
                    looking_for = ?, linkedin_url = ?, cam_email = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    payload["first_name"],
                    payload["last_name"],
                    payload["college"],
                    payload["course"],
                    payload["year"],
                    payload["what_have_you_built"],
                    serialized_skills,
                    payload["commitment_level"],
                    payload["looking_for"],
                    payload["linkedin_url"],
                    payload["cam_email"],
                    timestamp,
                    user_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO profiles (
                    user_id, first_name, last_name, college, course, year,
                    what_have_you_built, skills_json, commitment_level, looking_for,
                    linkedin_url, cam_email, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    payload["first_name"],
                    payload["last_name"],
                    payload["college"],
                    payload["course"],
                    payload["year"],
                    payload["what_have_you_built"],
                    serialized_skills,
                    payload["commitment_level"],
                    payload["looking_for"],
                    payload["linkedin_url"],
                    payload["cam_email"],
                    timestamp,
                    timestamp,
                ),
            )
        conn.commit()
    return get_profile(user_id)  # type: ignore[return-value]


def update_profile_photo_path(user_id: int, relative_path: str) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            "UPDATE profiles SET profile_photo_path = ?, updated_at = ? WHERE user_id = ?",
            (relative_path, now_iso(), user_id),
        )
        conn.commit()
    return get_profile(user_id)  # type: ignore[return-value]


def get_usage_count(user_id: int, action_type: str) -> int:
    usage_date = now_utc().date().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT count
            FROM daily_usage_tracking
            WHERE user_id = ? AND usage_date = ? AND action_type = ?
            """,
            (user_id, usage_date, action_type),
        ).fetchone()
        return int(row["count"]) if row else 0


def increment_usage(user_id: int, action_type: str) -> int:
    usage_date = now_utc().date().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, count
            FROM daily_usage_tracking
            WHERE user_id = ? AND usage_date = ? AND action_type = ?
            """,
            (user_id, usage_date, action_type),
        ).fetchone()
        if row:
            new_count = int(row["count"]) + 1
            conn.execute(
                "UPDATE daily_usage_tracking SET count = ? WHERE id = ?",
                (new_count, row["id"]),
            )
        else:
            new_count = 1
            conn.execute(
                """
                INSERT INTO daily_usage_tracking (user_id, usage_date, action_type, count)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, usage_date, action_type, new_count),
            )
        conn.commit()
        return new_count


def get_all_profiles(exclude_user_id: int | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT profiles.*, users.email, users.is_demo
        FROM profiles
        JOIN users ON users.id = profiles.user_id
    """
    params: tuple[Any, ...] = ()
    if exclude_user_id is not None:
        query += " WHERE profiles.user_id != ?"
        params = (exclude_user_id,)
    query += " ORDER BY profiles.updated_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = row_to_profile(row)
            if item:
                item["email"] = row["email"]
                item["is_demo"] = bool(row["is_demo"])
                results.append(item)
        return results


def get_request_between_users(user_a_id: int, user_b_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM connect_requests
            WHERE (sender_user_id = ? AND recipient_user_id = ?)
               OR (sender_user_id = ? AND recipient_user_id = ?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_a_id, user_b_id, user_b_id, user_a_id),
        ).fetchone()
        return dict(row) if row else None


def create_connect_request(sender_user_id: int, recipient_user_id: int, message: str) -> dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO connect_requests (
                sender_user_id, recipient_user_id, message, status, created_at
            )
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (sender_user_id, recipient_user_id, message, now_iso()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM connect_requests WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)


def update_request_status(request_id: int, status: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE connect_requests
            SET status = ?, responded_at = ?
            WHERE id = ?
            """,
            (status, now_iso(), request_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM connect_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None


def get_connect_request(request_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM connect_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None


def list_connect_requests(user_id: int) -> dict[str, list[dict[str, Any]]]:
    query = """
        SELECT
            connect_requests.*,
            profiles.user_id AS profile_user_id,
            profiles.first_name,
            profiles.last_name,
            profiles.college,
            profiles.course,
            profiles.year,
            profiles.commitment_level,
            profiles.skills_json,
            profiles.profile_photo_path
        FROM connect_requests
        JOIN profiles ON profiles.user_id =
            CASE
                WHEN connect_requests.sender_user_id = ? THEN connect_requests.recipient_user_id
                ELSE connect_requests.sender_user_id
            END
        WHERE connect_requests.sender_user_id = ? OR connect_requests.recipient_user_id = ?
        ORDER BY connect_requests.created_at DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (user_id, user_id, user_id)).fetchall()

    incoming: list[dict[str, Any]] = []
    outgoing: list[dict[str, Any]] = []
    for row in rows:
        counterparty_user_id = row["recipient_user_id"] if row["sender_user_id"] == user_id else row["sender_user_id"]
        avatar_url = avatar_url_for_profile(
            row["profile_user_id"],
            row["first_name"],
            row["last_name"],
            row["profile_photo_path"],
        )
        item = {
            "id": row["id"],
            "sender_user_id": row["sender_user_id"],
            "recipient_user_id": row["recipient_user_id"],
            "message": row["message"],
            "status": row["status"],
            "created_at": row["created_at"],
            "responded_at": row["responded_at"],
            "counterparty": {
                "user_id": counterparty_user_id,
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "college": row["college"],
                "course": row["course"],
                "year": row["year"],
                "commitment_level": row["commitment_level"],
                "skills": json.loads(row["skills_json"]),
                "avatar_url": avatar_url,
            },
        }
        if row["recipient_user_id"] == user_id:
            incoming.append(item)
        else:
            outgoing.append(item)
    return {"incoming": incoming, "outgoing": outgoing}


def list_accepted_connections(user_id: int) -> list[dict[str, Any]]:
    query = """
        SELECT
            connect_requests.id AS request_id,
            connect_requests.created_at AS request_created_at,
            connect_requests.responded_at AS request_responded_at,
            profiles.*,
            users.is_demo
        FROM connect_requests
        JOIN profiles ON profiles.user_id =
            CASE
                WHEN connect_requests.sender_user_id = ? THEN connect_requests.recipient_user_id
                ELSE connect_requests.sender_user_id
            END
        JOIN users ON users.id = profiles.user_id
        WHERE connect_requests.status = 'accepted'
          AND (connect_requests.sender_user_id = ? OR connect_requests.recipient_user_id = ?)
        ORDER BY COALESCE(connect_requests.responded_at, connect_requests.created_at) DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (user_id, user_id, user_id)).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        profile = row_to_profile(row)
        if not profile:
            continue
        results.append(
            {
                "request_id": row["request_id"],
                "connected_on": row["request_responded_at"] or row["request_created_at"],
                "counterparty": {
                    "user_id": profile["user_id"],
                    "first_name": profile["first_name"],
                    "last_name": profile["last_name"],
                    "college": profile["college"],
                    "course": profile["course"],
                    "year": profile["year"],
                    "skills": profile["skills"],
                    "commitment_level": profile["commitment_level"],
                    "looking_for": profile["looking_for"],
                    "avatar_url": profile["avatar_url"],
                    "linkedin_url": None if row["is_demo"] else profile["linkedin_url"],
                    "cam_email": None if row["is_demo"] else profile["cam_email"],
                },
            }
        )
    return results


def contact_unlocked(viewer_user_id: int, target_user_id: int) -> bool:
    if viewer_user_id == target_user_id:
        return True
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM connect_requests
            WHERE status = 'accepted'
              AND (
                (sender_user_id = ? AND recipient_user_id = ?)
                OR (sender_user_id = ? AND recipient_user_id = ?)
              )
            LIMIT 1
            """,
            (viewer_user_id, target_user_id, target_user_id, viewer_user_id),
        ).fetchone()
        return row is not None


def skill_targets(looking_for: str) -> set[str]:
    if looking_for == "Technical":
        return {"Engineering"}
    if looking_for == "Non-technical":
        return {"Product", "Business"}
    return set(SKILLS)


def compute_match_score(viewer: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if viewer["commitment_level"] == candidate["commitment_level"]:
        score += 40
        reasons.append("Same commitment level")

    candidate_skills = set(candidate["skills"])
    viewer_skills = set(viewer["skills"])

    if candidate_skills & skill_targets(viewer["looking_for"]):
        score += 25
        reasons.append("Matches what you are looking for")

    if viewer_skills & skill_targets(candidate["looking_for"]):
        score += 15
        reasons.append("You match what they are looking for")

    if candidate_skills - viewer_skills:
        score += 10
        reasons.append("Brings complementary skills")

    if viewer["college"].strip().lower() == candidate["college"].strip().lower():
        score += 8
        reasons.append("Same college")

    score -= len(candidate_skills & viewer_skills) * 2

    return score, reasons


def seed_demo_data() -> None:
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        if existing and existing["count"] > 0:
            return

        users = [
            ("demo@cambridgecofounder.local", 1),
            ("alice@cam.ac.uk", 0),
            ("ben@cam.ac.uk", 0),
            ("clara@cam.ac.uk", 0),
            ("dev@cam.ac.uk", 0),
            ("eva@cam.ac.uk", 0),
            ("farah@cam.ac.uk", 0),
        ]
        user_ids: dict[str, int] = {}
        timestamp = now_iso()
        for email, is_demo in users:
            cursor = conn.execute(
                "INSERT INTO users (email, is_demo, created_at) VALUES (?, ?, ?)",
                (email, is_demo, timestamp),
            )
            user_ids[email] = int(cursor.lastrowid)

        profiles = [
            {
                "email": "demo@cambridgecofounder.local",
                "first_name": "Demo",
                "last_name": "User",
                "college": "King's",
                "course": "Computer Science",
                "year": 2,
                "what_have_you_built": "Built a lightweight demo profile so visitors can explore the product without touching real contact details.",
                "skills": ["Product", "Business"],
                "commitment_level": "Serious",
                "looking_for": "Technical",
                "linkedin_url": "",
                "cam_email": "demo@cambridgecofounder.local",
            },
            {
                "email": "alice@cam.ac.uk",
                "first_name": "Alice",
                "last_name": "Morgan",
                "college": "Trinity",
                "course": "Engineering",
                "year": 3,
                "what_have_you_built": "Shipped a hackathon logistics tool used by two student societies and prototyped a carbon reporting dashboard for labs.",
                "skills": ["Engineering", "Product"],
                "commitment_level": "Serious",
                "looking_for": "Either",
                "linkedin_url": "https://www.linkedin.com/in/alicemorgan-cambridge",
                "cam_email": "alice@cam.ac.uk",
            },
            {
                "email": "ben@cam.ac.uk",
                "first_name": "Ben",
                "last_name": "Patel",
                "college": "St John's",
                "course": "Economics",
                "year": 2,
                "what_have_you_built": "Led go-to-market for a student marketplace, closed sponsorships for a conference, and now wants to pair with a technical builder.",
                "skills": ["Business"],
                "commitment_level": "Part-time",
                "looking_for": "Technical",
                "linkedin_url": "https://www.linkedin.com/in/benpatel-cambridge",
                "cam_email": "ben@cam.ac.uk",
            },
            {
                "email": "clara@cam.ac.uk",
                "first_name": "Clara",
                "last_name": "Zhou",
                "college": "King's",
                "course": "Computer Science",
                "year": 1,
                "what_have_you_built": "Built internal tooling for a research lab and a small AI note-taking product with fifty weekly student users.",
                "skills": ["Engineering"],
                "commitment_level": "Serious",
                "looking_for": "Non-technical",
                "linkedin_url": "https://www.linkedin.com/in/clarazhou-cambridge",
                "cam_email": "clara@cam.ac.uk",
            },
            {
                "email": "dev@cam.ac.uk",
                "first_name": "Dev",
                "last_name": "Singh",
                "college": "Downing",
                "course": "Land Economy",
                "year": 4,
                "what_have_you_built": "Ran customer interviews for a proptech concept, built the early product spec, and tested pricing with local landlords.",
                "skills": ["Product", "Business"],
                "commitment_level": "Exploring",
                "looking_for": "Technical",
                "linkedin_url": "https://www.linkedin.com/in/devsingh-cambridge",
                "cam_email": "dev@cam.ac.uk",
            },
            {
                "email": "eva@cam.ac.uk",
                "first_name": "Eva",
                "last_name": "Reed",
                "college": "Trinity",
                "course": "Natural Sciences",
                "year": 3,
                "what_have_you_built": "Built a wet-lab inventory tracker and a no-code pilot for researchers who need better procurement workflows.",
                "skills": ["Product"],
                "commitment_level": "Part-time",
                "looking_for": "Technical",
                "linkedin_url": "https://www.linkedin.com/in/evareed-cambridge",
                "cam_email": "eva@cam.ac.uk",
            },
            {
                "email": "farah@cam.ac.uk",
                "first_name": "Farah",
                "last_name": "Ahmed",
                "college": "Churchill",
                "course": "Mathematics",
                "year": 2,
                "what_have_you_built": "Built a tutoring marketplace MVP, handled early growth, and wants a serious partner to take the platform further.",
                "skills": ["Business", "Product"],
                "commitment_level": "Serious",
                "looking_for": "Technical",
                "linkedin_url": "https://www.linkedin.com/in/farahahmed-cambridge",
                "cam_email": "farah@cam.ac.uk",
            },
        ]

        for item in profiles:
            conn.execute(
                """
                INSERT INTO profiles (
                    user_id, first_name, last_name, college, course, year,
                    what_have_you_built, skills_json, commitment_level, looking_for,
                    linkedin_url, cam_email, profile_photo_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_ids[item["email"]],
                    item["first_name"],
                    item["last_name"],
                    item["college"],
                    item["course"],
                    item["year"],
                    item["what_have_you_built"],
                    json.dumps(item["skills"]),
                    item["commitment_level"],
                    item["looking_for"],
                    item["linkedin_url"],
                    item["cam_email"],
                    None,
                    timestamp,
                    timestamp,
                ),
            )

        connect_requests = [
            (user_ids["alice@cam.ac.uk"], user_ids["clara@cam.ac.uk"], "Building workflow tooling for labs. Would love to compare notes.", "accepted"),
            (user_ids["ben@cam.ac.uk"], user_ids["alice@cam.ac.uk"], "Working on a student finance product. Keen to chat if you are exploring ideas.", "pending"),
            (user_ids["eva@cam.ac.uk"], user_ids["farah@cam.ac.uk"], "You seem strong on distribution. Want to swap ideas on campus acquisition?", "declined"),
        ]

        for sender_id, recipient_id, message, status in connect_requests:
            responded_at = timestamp if status != "pending" else None
            conn.execute(
                """
                INSERT INTO connect_requests (
                    sender_user_id, recipient_user_id, message, status, created_at, responded_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sender_id, recipient_id, message, status, timestamp, responded_at),
            )

        conn.commit()
