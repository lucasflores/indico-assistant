# Indico Assistant

An intelligent, self-hosted conversational assistant for [Indico](https://github.com/indico/indico), the popular open-source event management system. The assistant interprets natural language questions about events, users, and files, generates SQL queries dynamically, and provides structured, conversational responses.

## ✨ Features

- **Natural Language to SQL**: Ask questions in plain English and get intelligent SQL queries generated automatically
- **Vector Search & RAG**: Semantic search through attached documents (PDFs, slides, etc.) using pgvector
- **Conversational Interface**: Clean, interactive chat interface powered by Chainlit
- **Event Management Integration**: Deep integration with Indico's event, meeting, and registration systems
- **Smart Query Classification**: Automatically categorizes queries (events, meetings, registrations) for better context
- **SQL Error Recovery**: Automatic correction of failed SQL queries using LLM feedback
- **Security & Guardrails**: Built-in safety measures to prevent SQL injection and malicious queries

## 🏗️ Architecture

The assistant combines several powerful technologies:

- **LLMs**: Hugging Face Inference API for query interpretation, SQL generation, and result summarization
- **Chainlit**: Interactive chat-based frontend for seamless user experience
- **PostgreSQL + pgvector**: Structured and semantic data storage with vector search capabilities
- **SQLAlchemy**: Database ORM for safe and efficient database operations
- **Indico Integration**: Native integration with Indico's Flask backend and data models

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- PostgreSQL database with pgvector extension
- Indico instance (for full functionality)
- Hugging Face API token

### Installation

1. **Clone and install the package:**
   ```bash
   cd /path/to/indico/plugins_lucas/indico_assistant
   pip install -e .
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   ```bash
   export HF_TOKEN="your_huggingface_token"
   export INDICO_DB_URL="postgresql+psycopg2://user:password@localhost:5432/indico"
   export INVARIANT_API_KEY="your_invariant_api_key"  # Optional: for advanced guardrails
   ```

4. **Configure database schema:**
   - Ensure your database schema is properly defined in `src/config/all_tables.yaml`
   - Update `src/config/available_tables.yaml` with tables you want to expose

5. **Run the assistant:**
   ```bash
   cd src
   chainlit run app_chnlit.py
   ```

The assistant will be available at `http://localhost:8000`

## 🎯 Usage Examples

### Event Queries
- *"Show me all conferences scheduled for next month"*
- *"What meetings are happening today?"*
- *"Find events with 'AI' in the title from the last 6 months"*

### Meeting Management  
- *"List upcoming meetings with their agendas"*
- *"Show me meetings I'm attending this week"*
- *"What's the largest meeting happening tomorrow?"*

### Registration Insights
- *"How many people registered for the Python conference?"*
- *"Show registration trends for events this year"*
- *"List events with highest attendance rates"*

### Document Search
- *"Find presentations about machine learning in recent events"*
- *"Search for documents mentioning 'data science' in event materials"*

## 📁 Project Structure

```
indico_assistant/
├── src/
│   ├── app_chnlit.py           # Main Chainlit application
│   ├── query_tools.py          # Database query tools and utilities
│   ├── config.py               # Configuration management
│   ├── models.py               # Data models
│   ├── exceptions.py           # Custom exceptions
│   ├── interfaces.py           # Interface definitions
│   ├── config/
│   │   ├── all_tables.yaml     # Complete database schema
│   │   └── available_tables.yaml # Exposed tables configuration
│   ├── database/
│   │   ├── base.py             # Database connection setup
│   │   └── queries.py          # Query execution utilities
│   ├── prompts/
│   │   ├── classify_prompt.txt # Query classification prompt
│   │   ├── sql_prompt.txt      # SQL generation prompt
│   │   ├── summarize_prompt.txt # Result summarization prompt
│   │   └── sql_error_prompt.txt # Error correction prompt
│   └── utils/
│       └── sql.py              # SQL parsing and safety utilities
├── tests/
│   └── test_event_processing.py
├── requirements.txt
├── setup.py
└── chainlit.md                 # Chainlit welcome message
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `INDICO_DB_URL` | PostgreSQL connection string | `postgresql+psycopg2://lucasflores:@localhost:5432/indico` |
| `INDICO_DB_POOL_SIZE` | Database connection pool size | `5` |
| `INDICO_DB_MAX_OVERFLOW` | Max connections beyond pool size | `10` |
| `INDICO_DB_POOL_TIMEOUT` | Connection timeout (seconds) | `30` |
| `HF_TOKEN` | Hugging Face API token | Required |
| `INVARIANT_API_KEY` | Invariant guardrails API key | Optional |

### Database Schema

The assistant reads your database schema from `src/config/all_tables.yaml`. This file should contain:

- Table names and descriptions
- Column definitions with types and descriptions  
- Foreign key relationships
- Indexes and constraints

Example schema entry:
```yaml
Table: events.events
Description: Table containing information about events.
Columns:
- id: INTEGER — Unique identifier for the event.
- title: VARCHAR — The title of the event.
- start_dt: TIMESTAMP — Date and time when the event starts.
- timezone: VARCHAR — Timezone in which the event takes place.
Foreign Keys:
- (creator_id) → users.users(id)
```

## 🔧 Development

### Running Tests
```bash
cd tests
python -m pytest test_event_processing.py -v
```

### Adding New Query Types

1. Update the classification prompt in `src/prompts/classify_prompt.txt`
2. Add handling logic in `src/query_tools.py`
3. Test with various natural language inputs

### Customizing Prompts

All LLM prompts are stored in `src/prompts/` and can be customized:

- `classify_prompt.txt`: Intent classification
- `sql_prompt.txt`: SQL generation 
- `summarize_prompt.txt`: Result summarization
- `sql_error_prompt.txt`: Error correction

### Adding New Tools

The assistant uses a tool-based architecture. Add new tools in `src/query_tools.py`:

```python
def my_custom_tool(param: str) -> Dict[str, Any]:
    """Description of what the tool does."""
    # Implementation here
    return results
```

## 🛡️ Security

The assistant includes several security measures:

- **SQL Injection Prevention**: All queries are parameterized and validated
- **Read-Only Transactions**: Database operations are read-only by default
- **Query Filtering**: Dangerous SQL patterns are blocked
- **Guardrails Integration**: Optional integration with Invariant for advanced safety
- **Input Validation**: All user inputs are sanitized before processing

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📋 Requirements

See `requirements.txt` for the complete list of dependencies:

- `automaton_core` - Core automation framework
- `chainlit` - Chat interface framework
- `sqlalchemy` - Database ORM
- `psycopg2-binary` - PostgreSQL adapter
- `huggingface_hub` - Hugging Face API client
- `sentence_transformers` - Text embeddings
- `pyyaml` - YAML configuration parsing
- `indico` - Indico event management system

## 📜 License

This project is part of the Indico ecosystem. Please refer to Indico's licensing terms.

## 🆘 Support

For issues and questions:

1. Check the [Indico documentation](https://docs.getindico.io/)
2. Search existing issues in the repository
3. Create a new issue with detailed reproduction steps

## 🙏 Acknowledgments

- Built on top of the excellent [Indico](https://github.com/indico/indico) event management system
- Powered by [Chainlit](https://chainlit.io/) for the conversational interface
- Uses [Hugging Face](https://huggingface.co/) for state-of-the-art language models

---

*Transform your event management experience with intelligent, conversational queries. Ask questions naturally and get instant, accurate insights from your Indico data.*
