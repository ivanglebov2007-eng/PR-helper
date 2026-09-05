import psycopg2
import psycopg2.extras
from typing import Dict, List, Set, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import logging
import os

from config import DATABASE_URL

logger = logging.getLogger(__name__)

@dataclass
class RequestData:
    screenshot: str
    media_link: str
    channel_name: str
    subscribers: str
    contact_link: str
    conditions: str
    user_id: int
    created_at: str
    is_active: bool = True
    closed_by: Optional[int] = None
    closed_at: Optional[str] = None
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


class Database:
    def __init__(self, database_url: str = None):
        if database_url is None:
            database_url = DATABASE_URL
        
        self.database_url = database_url
        self.conn = None
        self.cursor = None
        self.pending_requests: Dict[int, dict] = {}
        
        self._connect()
        self._create_tables()
        logger.info(f"✅ PostgreSQL база данных инициализирована")
    
    def _connect(self):
        try:
            self.conn = psycopg2.connect(self.database_url)
            self.conn.autocommit = False
            self.cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            logger.info("✅ Подключение к PostgreSQL установлено")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            raise
    
    def _create_tables(self):
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    role VARCHAR(50) DEFAULT 'pr',
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS topics (
                    topic_id BIGINT PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    screenshot TEXT NOT NULL,
                    media_link TEXT NOT NULL,
                    channel_name VARCHAR(500) NOT NULL,
                    subscribers VARCHAR(100) NOT NULL,
                    contact_link TEXT NOT NULL,
                    conditions TEXT,
                    created_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    closed_by BIGINT,
                    closed_at TIMESTAMP
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_topics (
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    topic_id BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
                    PRIMARY KEY (user_id, topic_id)
                )
            ''')
            
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_channel ON topics(channel_name)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_active ON topics(is_active)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_user ON topics(user_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_created ON topics(created_at DESC)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_topics_user ON user_topics(user_id)')
            
            self.conn.commit()
            logger.info("✅ Таблицы созданы/обновлены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            self.conn.rollback()
            raise
    
    def _execute(self, query: str, params: tuple = ()):
        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor
        except Exception as e:
            logger.error(f"❌ Ошибка SQL: {query[:200]}\n{e}")
            self.conn.rollback()
            raise
    
    def _fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        self.cursor.execute(query, params)
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def _fetch_all(self, query: str, params: tuple = ()) -> List[dict]:
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]
    
    def add_user(self, user_id: int, username: str = None, full_name: str = None, role: str = 'pr') -> bool:
        try:
            self._execute('''
                INSERT INTO users (user_id, username, full_name, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    role = EXCLUDED.role
            ''', (user_id, username, full_name, role))
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя {user_id}: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[dict]:
        return self._fetch_one('SELECT * FROM users WHERE user_id = %s', (user_id,))
    
    def add_pr_manager(self, user_id: int) -> bool:
        return self.add_user(user_id, role='pr')
    
    def add_dep_chief(self, user_id: int) -> bool:
        return self.add_user(user_id, role='dep_chief')
    
    def add_chief(self, user_id: int) -> bool:
        return self.add_user(user_id, role='chief')
    
    def remove_user(self, user_id: int) -> bool:
        try:
            self._execute('DELETE FROM users WHERE user_id = %s', (user_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления пользователя {user_id}: {e}")
            return False
    
    def get_all_users(self) -> List[dict]:
        return self._fetch_all('SELECT * FROM users ORDER BY role, user_id')
    
    def get_pr_managers(self) -> List[int]:
        rows = self._fetch_all("SELECT user_id FROM users WHERE role IN ('pr', 'dep_chief')")
        return [row['user_id'] for row in rows]
    
    def get_dep_chiefs(self) -> List[int]:
        rows = self._fetch_all("SELECT user_id FROM users WHERE role = 'dep_chief'")
        return [row['user_id'] for row in rows]
    
    def is_pr_manager(self, user_id: int) -> bool:
        row = self._fetch_one(
            "SELECT user_id FROM users WHERE user_id = %s AND role IN ('pr', 'dep_chief')",
            (user_id,)
        )
        return row is not None
    
    def is_dep_chief(self, user_id: int) -> bool:
        row = self._fetch_one(
            "SELECT user_id FROM users WHERE user_id = %s AND role = 'dep_chief'",
            (user_id,)
        )
        return row is not None
    
    def is_chief(self, user_id: int) -> bool:
        row = self._fetch_one(
            "SELECT user_id FROM users WHERE user_id = %s AND role = 'chief'",
            (user_id,)
        )
        return row is not None
    
    def add_topic(self, topic_id: int, request_data: RequestData):
        try:
            self.add_user(request_data.user_id, role='pr')
            
            self._execute('''
                INSERT INTO topics (
                    topic_id, user_id, screenshot, media_link, channel_name,
                    subscribers, contact_link, conditions, created_at, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                topic_id,
                request_data.user_id,
                request_data.screenshot,
                request_data.media_link,
                request_data.channel_name,
                request_data.subscribers,
                request_data.contact_link,
                request_data.conditions,
                request_data.created_at,
                request_data.is_active
            ))
            
            self._execute('''
                INSERT INTO user_topics (user_id, topic_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, topic_id) DO NOTHING
            ''', (request_data.user_id, topic_id))
            
            logger.info(f"✅ Тема {topic_id} добавлена в БД")
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления темы {topic_id}: {e}")
            raise
    
    def close_topic(self, topic_id: int, closed_by: int) -> bool:
        try:
            self._execute('''
                UPDATE topics 
                SET is_active = FALSE, closed_by = %s, closed_at = %s
                WHERE topic_id = %s
            ''', (closed_by, datetime.now().isoformat(), topic_id))
            
            logger.info(f"✅ Тема {topic_id} закрыта")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия темы {topic_id}: {e}")
            return False
    
    def get_topic(self, topic_id: int) -> Optional[RequestData]:
        row = self._fetch_one('SELECT * FROM topics WHERE topic_id = %s', (topic_id,))
        if row:
            return RequestData(
                screenshot=row['screenshot'],
                media_link=row['media_link'],
                channel_name=row['channel_name'],
                subscribers=row['subscribers'],
                contact_link=row['contact_link'],
                conditions=row['conditions'] or "Не указаны",
                user_id=row['user_id'],
                created_at=row['created_at'],
                is_active=row['is_active'],
                closed_by=row['closed_by'],
                closed_at=row['closed_at']
            )
        return None
    
    def get_user_topics(self, user_id: int) -> List[int]:
        rows = self._fetch_all('''
            SELECT t.topic_id FROM topics t
            JOIN user_topics ut ON t.topic_id = ut.topic_id
            WHERE ut.user_id = %s
            ORDER BY t.created_at DESC
        ''', (user_id,))
        return [row['topic_id'] for row in rows]
    
    def get_active_topics(self) -> List[Tuple[int, RequestData]]:
        rows = self._fetch_all('''
            SELECT * FROM topics WHERE is_active = TRUE ORDER BY created_at DESC
        ''')
        result = []
        for row in rows:
            result.append((
                row['topic_id'],
                RequestData(
                    screenshot=row['screenshot'],
                    media_link=row['media_link'],
                    channel_name=row['channel_name'],
                    subscribers=row['subscribers'],
                    contact_link=row['contact_link'],
                    conditions=row['conditions'] or "Не указаны",
                    user_id=row['user_id'],
                    created_at=row['created_at'],
                    is_active=row['is_active'],
                    closed_by=row['closed_by'],
                    closed_at=row['closed_at']
                )
            ))
        return result
    
    def get_closed_topics(self) -> List[Tuple[int, RequestData]]:
        rows = self._fetch_all('''
            SELECT * FROM topics WHERE is_active = FALSE ORDER BY closed_at DESC
        ''')
        result = []
        for row in rows:
            result.append((
                row['topic_id'],
                RequestData(
                    screenshot=row['screenshot'],
                    media_link=row['media_link'],
                    channel_name=row['channel_name'],
                    subscribers=row['subscribers'],
                    contact_link=row['contact_link'],
                    conditions=row['conditions'] or "Не указаны",
                    user_id=row['user_id'],
                    created_at=row['created_at'],
                    is_active=row['is_active'],
                    closed_by=row['closed_by'],
                    closed_at=row['closed_at']
                )
            ))
        return result
    
    def search_topics(self, keyword: str, include_archived: bool = False) -> List[Tuple[int, RequestData]]:
        keyword = f"%{keyword}%"
        
        query = '''
            SELECT * FROM topics 
            WHERE (channel_name ILIKE %s OR conditions ILIKE %s)
        '''
        params = (keyword, keyword)
        
        if not include_archived:
            query += " AND is_active = TRUE"
        
        query += " ORDER BY created_at DESC"
        
        rows = self._fetch_all(query, params)
        result = []
        for row in rows:
            result.append((
                row['topic_id'],
                RequestData(
                    screenshot=row['screenshot'],
                    media_link=row['media_link'],
                    channel_name=row['channel_name'],
                    subscribers=row['subscribers'],
                    contact_link=row['contact_link'],
                    conditions=row['conditions'] or "Не указаны",
                    user_id=row['user_id'],
                    created_at=row['created_at'],
                    is_active=row['is_active'],
                    closed_by=row['closed_by'],
                    closed_at=row['closed_at']
                )
            ))
        return result
    
    def get_statistics(self) -> dict:
        stats = self._fetch_one('''
            SELECT 
                COUNT(*) as total_topics,
                COUNT(CASE WHEN is_active = TRUE THEN 1 END) as active_topics,
                COUNT(CASE WHEN is_active = FALSE THEN 1 END) as closed_topics,
                (SELECT COUNT(*) FROM users) as total_users,
                (SELECT COUNT(*) FROM users WHERE role = 'pr') as pr_count,
                (SELECT COUNT(*) FROM users WHERE role = 'dep_chief') as dep_chief_count
            FROM topics
        ''')
        return stats if stats else {
            'total_topics': 0,
            'active_topics': 0,
            'closed_topics': 0,
            'total_users': 0,
            'pr_count': 0,
            'dep_chief_count': 0
        }
    
    def get_pending_request(self, user_id: int) -> Optional[dict]:
        return self.pending_requests.get(user_id)
    
    def set_pending_request(self, user_id: int, data: dict):
        self.pending_requests[user_id] = data
    
    def clear_pending_request(self, user_id: int):
        self.pending_requests.pop(user_id, None)
    
    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("✅ Соединение с PostgreSQL закрыто")
