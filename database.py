import os
import json
from typing import Dict, List, Set, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import logging

from config import DATA_FILE

logger = logging.getLogger(__name__)

@dataclass
class RequestData:
    """Модель данных запроса"""
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
    """Класс для работы с базой данных"""
    
    def __init__(self, file_path: str = DATA_FILE):
        # Создаем папку для данных, если её нет
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        self.file_path = file_path
        self.pr_managers: Set[int] = set()
        self.dep_chiefs: Set[int] = set()
        self.topics: Dict[int, RequestData] = {}
        self.user_requests: Dict[int, List[int]] = {}
        self.pending_requests: Dict[int, dict] = {}
        
        self.load()
        
    def load(self):
        """Загрузка данных из файла"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                self.pr_managers = set(data.get('pr_managers', []))
                self.dep_chiefs = set(data.get('dep_chiefs', []))
                
                # Загружаем темы
                self.topics = {}
                for topic_id, topic_data in data.get('topics', {}).items():
                    self.topics[int(topic_id)] = RequestData.from_dict(topic_data)
                
                # Загружаем запросы пользователей
                self.user_requests = {}
                for user_id, topics in data.get('user_requests', {}).items():
                    self.user_requests[int(user_id)] = topics
                    
                logger.info(f"Загружено {len(self.topics)} тем и {len(self.pr_managers)} PR менеджеров")
                
        except FileNotFoundError:
            logger.info("Файл базы данных не найден, создаем новый")
            self.save()
        except Exception as e:
            logger.error(f"Ошибка загрузки базы данных: {e}")
            self.save()
        
    def save(self):
        """Сохранение данных в файл"""
        try:
            data = {
                'pr_managers': list(self.pr_managers),
                'dep_chiefs': list(self.dep_chiefs),
                'topics': {str(k): v.to_dict() for k, v in self.topics.items()},
                'user_requests': {str(k): v for k, v in self.user_requests.items()}
            }
            
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.info("База данных сохранена")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения базы данных: {e}")
    
    def add_pr_manager(self, user_id: int) -> bool:
        """Добавление PR менеджера"""
        if user_id not in self.pr_managers:
            self.pr_managers.add(user_id)
            self.save()
            return True
        return False
    
    def remove_pr_manager(self, user_id: int) -> bool:
        """Удаление PR менеджера"""
        if user_id in self.pr_managers:
            self.pr_managers.remove(user_id)
            self.save()
            return True
        return False
    
    def add_dep_chief(self, user_id: int) -> bool:
        """Добавление заместителя"""
        if user_id not in self.dep_chiefs:
            self.dep_chiefs.add(user_id)
            # Автоматически добавляем как PR
            self.add_pr_manager(user_id)
            self.save()
            return True
        return False
    
    def remove_dep_chief(self, user_id: int) -> bool:
        """Удаление заместителя"""
        if user_id in self.dep_chiefs:
            self.dep_chiefs.remove(user_id)
            self.save()
            return True
        return False
    
    def add_topic(self, topic_id: int, request_data: RequestData):
        """Добавление новой темы"""
        self.topics[topic_id] = request_data
        
        # Добавляем связь с пользователем
        user_id = request_data.user_id
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        self.user_requests[user_id].append(topic_id)
        
        self.save()
    
    def close_topic(self, topic_id: int, closed_by: int) -> bool:
        """Закрытие темы"""
        if topic_id in self.topics:
            topic = self.topics[topic_id]
            topic.is_active = False
            topic.closed_by = closed_by
            topic.closed_at = datetime.now().isoformat()
            self.save()
            return True
        return False
    
    def get_user_topics(self, user_id: int) -> List[int]:
        """Получение списка тем пользователя"""
        return self.user_requests.get(user_id, [])
    
    def search_topics(self, keyword: str) -> List[tuple]:
        """Поиск тем по ключевому слову"""
        results = []
        keyword = keyword.lower()
        
        for topic_id, data in self.topics.items():
            if not data.is_active:
                continue
                
            if (keyword in data.channel_name.lower() or 
                keyword in data.conditions.lower()):
                results.append((topic_id, data))
                
        return results
    
    def get_pending_request(self, user_id: int) -> Optional[dict]:
        """Получение временных данных запроса"""
        return self.pending_requests.get(user_id)
    
    def set_pending_request(self, user_id: int, data: dict):
        """Установка временных данных запроса"""
        self.pending_requests[user_id] = data
    
    def clear_pending_request(self, user_id: int):
        """Очистка временных данных запроса"""
        self.pending_requests.pop(user_id, None)
