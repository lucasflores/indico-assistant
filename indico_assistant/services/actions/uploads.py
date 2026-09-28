"""Files sent in the chat (US9, research R7): checked, and kept as unclaimed Indico files until a confirmed
attach_file step copies them into an attachment. Indico deletes unclaimed files after a day on its own.

Indico has no allowlist of attachment types and no size limit by default, and Chainlit only checks the
type the browser reports, so the plugin checks both here, by extension and by the file's content.
"""

import io

from indico.core.config import config
from indico.modules.files.models.files import File
from indico.util.fs import secure_client_filename


MAX_MB = 25  # per file (FR-024)
MAX_FILES = 5  # per message

_ZIP = b'PK\x03\x04'  # docx, pptx and xlsx are zip packages
_OFFICE = 'application/vnd.openxmlformats-officedocument.'
ALLOWED = {
    '.pdf': ('application/pdf', b'%PDF-'),
    '.docx': (_OFFICE + 'wordprocessingml.document', _ZIP),
    '.pptx': (_OFFICE + 'presentationml.presentation', _ZIP),
    '.xlsx': (_OFFICE + 'spreadsheetml.sheet', _ZIP),
    '.png': ('image/png', b'\x89PNG\r\n\x1a\n'),
    '.jpg': ('image/jpeg', b'\xff\xd8\xff'),
    '.jpeg': ('image/jpeg', b'\xff\xd8\xff'),
    '.txt': ('text/plain', None),
    '.md': ('text/markdown', None),
}
ALLOWED_NAMES = 'pdf, docx, pptx, xlsx, txt, md, png, jpg'


class UploadRefused(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def max_bytes():
    limits = [MAX_MB] + ([config.MAX_UPLOAD_FILE_SIZE] if config.MAX_UPLOAD_FILE_SIZE else [])
    return min(limits) * 1024 * 1024


def content_type(filename, data):
    """The file's type from its name, if its content really is that type; else UploadRefused."""
    extension = ('.' + filename.rsplit('.', 1)[-1].lower()) if '.' in filename else ''
    if extension not in ALLOWED:
        raise UploadRefused('UNSUPPORTED_FILE_TYPE', f'Allowed: {ALLOWED_NAMES}')
    mime, magic = ALLOWED[extension]
    if magic is not None:
        ok = data.startswith(magic)
    else:
        try:
            data.decode('utf-8')
            ok = b'\x00' not in data
        except UnicodeDecodeError:
            ok = False
    if not ok:
        raise UploadRefused('UNSUPPORTED_FILE_TYPE', f'This is not a {extension[1:]} file. Allowed: {ALLOWED_NAMES}')
    return mime


def store(user, stream, filename, chat_session_id=None):
    """Keep an uploaded file for ``user``; returns the unclaimed Indico ``File``."""
    limit = max_bytes()
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise UploadRefused('FILE_TOO_LARGE', f'Files can be at most {limit // (1024 * 1024)} MB')
    if not data:
        raise UploadRefused('EMPTY_FILE', 'The file is empty')
    name = secure_client_filename(filename)
    file = File.create_from_stream(io.BytesIO(data), name, content_type(name, data), ('assistant', str(user.id)))
    # File has no owner column: who uploaded it (and in which chat) decides who may use it (FR-025)
    file.meta = {'assistant_user_id': user.id, 'chat_session_id': str(chat_session_id) if chat_session_id else None}
    return file


def usable_upload(uuid, user):
    """The user's own, still unclaimed upload with this uuid, or None."""
    file = File.query.filter_by(uuid=str(uuid), claimed=False).first()
    if file is None or (file.meta or {}).get('assistant_user_id') != user.id:
        return None
    return file
