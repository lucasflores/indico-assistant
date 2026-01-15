# Data Model: Chat REST API

**Feature**: 004-chat-api | **Date**: 2026-01-14

## Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   ChatSession   │       │   ChatMessage   │       │  FeedbackEntry  │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │───┐   │ id (PK)         │───┐   │ id (PK)         │
│ user_id (FK)    │   │   │ session_id (FK) │   │   │ message_id (FK) │
│ event_id (FK)   │   └──<│ role            │   └──<│ user_id (FK)    │
│ created_at      │       │ content         │       │ feedback_type   │
│ updated_at      │       │ metadata_json   │       │ value           │
└─────────────────┘       │ created_at      │       │ created_at      │
                          └─────────────────┘       └─────────────────┘

Legend:
  (PK) = Primary Key
  (FK) = Foreign Key (conceptual - user/event from Indico core)
  ──< = One-to-Many relationship
```

## Table Definitions

### plugin_assistant.chat_sessions

Represents a conversation thread between a user and the assistant.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Unique session identifier |
| `user_id` | INTEGER | NOT NULL, INDEX | Indico user ID who owns the session |
| `event_id` | INTEGER | NULLABLE, INDEX | Optional event scope (NULL = global) |
| `created_at` | TIMESTAMP WITH TZ | NOT NULL, DEFAULT NOW() | Session creation time |
| `updated_at` | TIMESTAMP WITH TZ | NOT NULL, DEFAULT NOW(), INDEX | Last activity time (for 90-day cleanup) |

**Indexes**:
- `ix_chat_sessions_user_id` on (user_id)
- `ix_chat_sessions_event_id` on (event_id) WHERE event_id IS NOT NULL
- `ix_chat_sessions_updated_at` on (updated_at) - for cleanup queries

**Notes**:
- `user_id` references Indico's `users.users.id` (not enforced by FK for plugin isolation)
- `event_id` references Indico's `events.events.id` (not enforced by FK for plugin isolation)
- UUID used for `id` to prevent enumeration attacks

---

### plugin_assistant.chat_messages

Stores individual messages within a conversation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Unique message identifier |
| `session_id` | UUID | NOT NULL, FK → chat_sessions.id ON DELETE CASCADE, INDEX | Parent session |
| `role` | VARCHAR(16) | NOT NULL, CHECK IN ('user', 'assistant') | Message sender role |
| `content` | TEXT | NOT NULL | Message text content |
| `metadata_json` | JSONB | NULLABLE | Additional metadata (SQL, confidence, sources, etc.) |
| `created_at` | TIMESTAMP WITH TZ | NOT NULL, DEFAULT NOW(), INDEX | Message creation time |

**Indexes**:
- `ix_chat_messages_session_id` on (session_id)
- `ix_chat_messages_created_at` on (created_at) - for ordering

**Notes**:
- `metadata_json` stores assistant-specific data (generated SQL, confidence scores, data sources)
- Messages cascade-deleted when session is deleted
- Content limited to 10,000 characters (enforced at application layer)

---

### plugin_assistant.feedback_entries

Stores user feedback on assistant responses.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT uuid_generate_v4() | Unique feedback identifier |
| `message_id` | UUID | NOT NULL, FK → chat_messages.id ON DELETE CASCADE, INDEX | Target message |
| `user_id` | INTEGER | NOT NULL, INDEX | User providing feedback |
| `feedback_type` | VARCHAR(32) | NOT NULL, CHECK IN ('thumbs_up', 'thumbs_down', 'rating', 'comment') | Type of feedback |
| `value` | TEXT | NOT NULL | Feedback value (boolean string, 1-5, or text) |
| `created_at` | TIMESTAMP WITH TZ | NOT NULL, DEFAULT NOW() | Feedback submission time |

**Indexes**:
- `ix_feedback_entries_message_id` on (message_id)
- `ix_feedback_entries_user_id` on (user_id)
- UNIQUE constraint on (message_id, user_id, feedback_type) - one feedback per type per user per message

**Notes**:
- `value` is TEXT to accommodate all feedback types (boolean, integer, string)
- Application layer validates value matches feedback_type
- UNIQUE constraint allows updating feedback (upsert pattern)

---

## SQLAlchemy Models

### ChatSession

```python
class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    __table_args__ = {'schema': 'plugin_assistant'}
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    event_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    
    # Relationships
    messages = db.relationship('ChatMessage', backref='session', lazy='dynamic', cascade='all, delete-orphan')
```

### ChatMessage

```python
class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    __table_args__ = {'schema': 'plugin_assistant'}
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey('plugin_assistant.chat_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(JSONB, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    feedback = db.relationship('FeedbackEntry', backref='message', lazy='dynamic', cascade='all, delete-orphan')
```

### FeedbackEntry

```python
class FeedbackEntry(db.Model):
    __tablename__ = 'feedback_entries'
    __table_args__ = (
        db.UniqueConstraint('message_id', 'user_id', 'feedback_type', name='uq_feedback_per_user_type'),
        {'schema': 'plugin_assistant'}
    )
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = db.Column(UUID(as_uuid=True), db.ForeignKey('plugin_assistant.chat_messages.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    feedback_type = db.Column(db.String(32), nullable=False)  # thumbs_up, thumbs_down, rating, comment
    value = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)
```

---

## Pydantic Schemas (Request/Response)

### Chat Request/Response

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: UUID | None = None
    event_id: int | None = None

class ChatResponse(BaseModel):
    response: str
    session_id: UUID
    message_id: UUID
    metadata: dict = Field(default_factory=dict)

class ChatErrorResponse(BaseModel):
    error: str
    message: str
    details: dict | None = None
```

### Session Listing

```python
class SessionListItem(BaseModel):
    session_id: UUID
    created_at: datetime
    last_message_at: datetime
    message_count: int
    event_id: int | None = None

class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]
    total: int
    limit: int
    offset: int
```

### Session Detail

```python
class MessageItem(BaseModel):
    message_id: UUID
    role: Literal['user', 'assistant']
    content: str
    created_at: datetime
    metadata: dict | None = None

class SessionDetailResponse(BaseModel):
    session_id: UUID
    event_id: int | None = None
    created_at: datetime
    messages: list[MessageItem]
```

### Feedback

```python
class FeedbackRequest(BaseModel):
    message_id: UUID
    feedback_type: Literal['thumbs_up', 'thumbs_down', 'rating', 'comment']
    value: str | int | bool
    
    @validator('value')
    def validate_value(cls, v, values):
        ft = values.get('feedback_type')
        if ft in ('thumbs_up', 'thumbs_down') and not isinstance(v, bool):
            raise ValueError('Thumbs feedback requires boolean value')
        if ft == 'rating' and (not isinstance(v, int) or not 1 <= v <= 5):
            raise ValueError('Rating must be integer 1-5')
        if ft == 'comment' and not isinstance(v, str):
            raise ValueError('Comment must be string')
        return v

class FeedbackResponse(BaseModel):
    feedback_id: UUID
    message: str = "Feedback recorded"
```

---

## Migration Strategy

### Migration: 002_create_chat_tables.py

```python
"""Create chat_sessions, chat_messages, feedback_entries tables.

Revision ID: 002_create_chat_tables
Create Date: 2026-01-14
"""

def upgrade():
    # Ensure UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # chat_sessions
    op.create_table(
        'chat_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('event_id', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema='plugin_assistant'
    )
    op.create_index('ix_chat_sessions_user_id', 'chat_sessions', ['user_id'], schema='plugin_assistant')
    op.create_index('ix_chat_sessions_event_id', 'chat_sessions', ['event_id'], schema='plugin_assistant')
    op.create_index('ix_chat_sessions_updated_at', 'chat_sessions', ['updated_at'], schema='plugin_assistant')
    
    # chat_messages
    op.create_table(
        'chat_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('session_id', UUID(as_uuid=True), sa.ForeignKey('plugin_assistant.chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('metadata_json', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('user', 'assistant')", name='ck_chat_messages_role'),
        schema='plugin_assistant'
    )
    op.create_index('ix_chat_messages_session_id', 'chat_messages', ['session_id'], schema='plugin_assistant')
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'], schema='plugin_assistant')
    
    # feedback_entries
    op.create_table(
        'feedback_entries',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('message_id', UUID(as_uuid=True), sa.ForeignKey('plugin_assistant.chat_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('feedback_type', sa.String(32), nullable=False),
        sa.Column('value', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("feedback_type IN ('thumbs_up', 'thumbs_down', 'rating', 'comment')", name='ck_feedback_type'),
        sa.UniqueConstraint('message_id', 'user_id', 'feedback_type', name='uq_feedback_per_user_type'),
        schema='plugin_assistant'
    )
    op.create_index('ix_feedback_entries_message_id', 'feedback_entries', ['message_id'], schema='plugin_assistant')
    op.create_index('ix_feedback_entries_user_id', 'feedback_entries', ['user_id'], schema='plugin_assistant')

def downgrade():
    op.drop_table('feedback_entries', schema='plugin_assistant')
    op.drop_table('chat_messages', schema='plugin_assistant')
    op.drop_table('chat_sessions', schema='plugin_assistant')
```

---

## Validation Rules

| Entity | Field | Rule |
|--------|-------|------|
| ChatMessage | content | 1-10,000 characters |
| ChatMessage | role | Must be 'user' or 'assistant' |
| FeedbackEntry | feedback_type | Must be in enum list |
| FeedbackEntry | value (thumbs) | Must be boolean |
| FeedbackEntry | value (rating) | Must be integer 1-5 |
| FeedbackEntry | value (comment) | Must be non-empty string |
| ChatSession | user_id | Must match authenticated user for access |

## State Transitions

### Session Lifecycle

```
[New Message w/o session_id]
           │
           ▼
    ┌─────────────┐
    │   CREATED   │ ◄── create_session()
    └──────┬──────┘
           │
    [Add message]
           │
           ▼
    ┌─────────────┐
    │   ACTIVE    │ ◄── add_message(), updated_at refreshed
    └──────┬──────┘
           │
    [90 days inactive OR user deletes]
           │
           ▼
    ┌─────────────┐
    │   DELETED   │ ◄── Cascade deletes messages + feedback
    └─────────────┘
```
