import json
import pickle
from pathlib import Path
from typing import Optional
from .buffer import ConversationBuffer

class MemoryStorage:
    """File-based conversation persistence"""
    
    def __init__(self, storage_dir: str = "~/.openclaw/workspace/voice-agent/data/memory"):
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, call_id: str, buffer: ConversationBuffer):
        """Save conversation buffer"""
        filepath = self.storage_dir / f"{call_id}.pkl"
        with open(filepath, 'wb') as f:
            pickle.dump(buffer, f)
    
    def load(self, call_id: str) -> Optional[ConversationBuffer]:
        """Load conversation buffer"""
        filepath = self.storage_dir / f"{call_id}.pkl"
        if not filepath.exists():
            return None
        
        with open(filepath, 'rb') as f:
            return pickle.load(f)
    
    def delete(self, call_id: str):
        """Delete conversation buffer"""
        filepath = self.storage_dir / f"{call_id}.pkl"
        if filepath.exists():
            filepath.unlink()
    
    def list_calls(self) -> list[str]:
        """List all stored call IDs"""
        return [f.stem for f in self.storage_dir.glob("*.pkl")]