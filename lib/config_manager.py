#!/usr/bin/env python3
"""
ClawAPI Config Manager - openclaw.json API 配置管理器
统一管理 providers、keys、models、fallbacks
"""

import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

class ClawAPIConfigManager:
    def __init__(self, config_path: str = None):
        """初始化配置管理器"""
        if config_path is None:
            config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        
        self.config_path = Path(config_path)
        
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        
        self.backup_dir = self.config_path.parent / "backups"
        self.backup_dir.mkdir(exist_ok=True)
    
    def _load_config(self) -> dict:
        """加载配置"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_config(self, config: dict, backup: bool = True):
        """保存配置（自动备份）"""
        if backup:
            self._backup()
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write('\n')
    
    def _backup(self):
        """备份当前配置"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"openclaw_{timestamp}.json"
        shutil.copy(self.config_path, backup_file)
        
        # 只保留最近 10 个备份
        backups = sorted(self.backup_dir.glob("openclaw_*.json"))
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                old_backup.unlink()
        
        return backup_file
    
    # ========== Provider 管理 ==========
    
    def list_providers(self) -> List[Dict]:
        """列出所有 providers"""
        config = self._load_config()
        providers = config.get('models', {}).get('providers', {})
        
        result = []
        for name, provider in providers.items():
            result.append({
                'name': name,
                'base_url': provider.get('baseURL', ''),
                'api_key': provider.get('apiKey', '')[:8] + '...' if provider.get('apiKey') else '(not set)',
                'model_count': len(provider.get('models', []))
            })
        
        return result
    
    def add_provider(self, name: str, base_url: str, api_key: str, 
                    models: List[Dict] = None):
        """添加新的 provider"""
        config = self._load_config()
        
        if 'models' not in config:
            config['models'] = {}
        if 'providers' not in config['models']:
            config['models']['providers'] = {}
        
        if name in config['models']['providers']:
            raise ValueError(f"Provider '{name}' already exists")
        
        config['models']['providers'][name] = {
            'baseURL': base_url,
            'apiKey': api_key,
            'models': models or []
        }
        
        self._save_config(config)
        return True
    
    def remove_provider(self, name: str):
        """删除 provider"""
        config = self._load_config()
        providers = config.get('models', {}).get('providers', {})
        
        if name not in providers:
            raise ValueError(f"Provider '{name}' not found")
        
        del providers[name]
        self._save_config(config)
        return True
    
    def update_api_key(self, provider_name: str, new_key: str):
        """更新 API key"""
        config = self._load_config()
        providers = config.get('models', {}).get('providers', {})
        
        if provider_name not in providers:
            raise ValueError(f"Provider '{provider_name}' not found")
        
        providers[provider_name]['apiKey'] = new_key
        self._save_config(config)
        return True
    
    # ========== Model 管理 ==========
    
    def list_models(self, provider_name: str = None) -> List[Dict]:
        """列出模型"""
        config = self._load_config()
        providers = config.get('models', {}).get('providers', {})
        
        result = []
        
        if provider_name:
            # 只列出指定 provider 的模型
            if provider_name not in providers:
                raise ValueError(f"Provider '{provider_name}' not found")
            
            for model in providers[provider_name].get('models', []):
                result.append({
                    'provider': provider_name,
                    'id': model['id'],
                    'name': model.get('name', model['id']),
                    'full_id': f"{provider_name}/{model['id']}"
                })
        else:
            # 列出所有模型
            for pname, provider in providers.items():
                for model in provider.get('models', []):
                    result.append({
                        'provider': pname,
                        'id': model['id'],
                        'name': model.get('name', model['id']),
                        'full_id': f"{pname}/{model['id']}"
                    })
        
        return result
    
    def add_model(self, provider_name: str, model_id: str, 
                 model_name: str = None, **kwargs):
        """添加模型到 provider"""
        config = self._load_config()
        providers = config.get('models', {}).get('providers', {})
        
        if provider_name not in providers:
            raise ValueError(f"Provider '{provider_name}' not found")
        
        model_data = {
            'id': model_id,
            'name': model_name or model_id,
            **kwargs
        }
        
        providers[provider_name]['models'].append(model_data)
        self._save_config(config)
        return True
    
    def remove_model(self, provider_name: str, model_id: str):
        """删除模型"""
        config = self._load_config()
        providers = config.get('models', {}).get('providers', {})
        
        if provider_name not in providers:
            raise ValueError(f"Provider '{provider_name}' not found")
        
        models = providers[provider_name]['models']
        providers[provider_name]['models'] = [
            m for m in models if m['id'] != model_id
        ]
        
        self._save_config(config)
        return True
    
    # ========== Primary & Fallback 管理 ==========
    
    def get_primary_model(self) -> str:
        """获取主模型"""
        config = self._load_config()
        return config.get('agents', {}).get('defaults', {}).get('model', {}).get('primary', '(not set)')
    
    def set_primary_model(self, model_id: str):
        """设置主模型"""
        config = self._load_config()
        
        if 'agents' not in config:
            config['agents'] = {}
        if 'defaults' not in config['agents']:
            config['agents']['defaults'] = {}
        if 'model' not in config['agents']['defaults']:
            config['agents']['defaults']['model'] = {}
        
        config['agents']['defaults']['model']['primary'] = model_id
        self._save_config(config)
        return True
    
    def get_fallbacks(self) -> List[str]:
        """获取 fallback 链"""
        config = self._load_config()
        return config.get('agents', {}).get('defaults', {}).get('model', {}).get('fallbacks', [])
    
    def set_fallbacks(self, fallback_list: List[str]):
        """设置 fallback 链"""
        config = self._load_config()
        
        if 'agents' not in config:
            config['agents'] = {}
        if 'defaults' not in config['agents']:
            config['agents']['defaults'] = {}
        if 'model' not in config['agents']['defaults']:
            config['agents']['defaults']['model'] = {}
        
        config['agents']['defaults']['model']['fallbacks'] = fallback_list
        self._save_config(config)
        return True
    
    def add_fallback(self, model_id: str):
        """添加 fallback 模型"""
        fallbacks = self.get_fallbacks()
        if model_id not in fallbacks:
            fallbacks.append(model_id)
            self.set_fallbacks(fallbacks)
        return True
    
    def remove_fallback(self, model_id: str):
        """删除 fallback 模型"""
        fallbacks = self.get_fallbacks()
        fallbacks = [f for f in fallbacks if f != model_id]
        self.set_fallbacks(fallbacks)
        return True
    
    # ========== 测试 & 验证 ==========
    
    def test_provider(self, provider_name: str) -> Dict:
        """测试 provider 连通性"""
        import requests
        
        config = self._load_config()
        providers = config.get('models', {}).get('providers', {})
        
        if provider_name not in providers:
            raise ValueError(f"Provider '{provider_name}' not found")
        
        provider = providers[provider_name]
        base_url = provider.get('baseURL', '')
        api_key = provider.get('apiKey', '')
        
        try:
            # 尝试调用 API
            response = requests.get(
                f"{base_url}/models",
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=5
            )
            
            return {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'message': 'OK' if response.status_code == 200 else response.text[:100]
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_config(self) -> Dict:
        """验证配置完整性"""
        config = self._load_config()
        issues = []
        
        # 检查 primary model
        primary = self.get_primary_model()
        if primary == '(not set)':
            issues.append("Primary model not set")
        
        # 检查 providers
        providers = config.get('models', {}).get('providers', {})
        if not providers:
            issues.append("No providers configured")
        
        for name, provider in providers.items():
            if not provider.get('apiKey'):
                issues.append(f"Provider '{name}' missing API key")
            if not provider.get('models'):
                issues.append(f"Provider '{name}' has no models")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }
    
    # ========== 备份 & 恢复 ==========
    
    def list_backups(self) -> List[Dict]:
        """列出所有备份"""
        backups = sorted(self.backup_dir.glob("openclaw_*.json"), reverse=True)
        
        result = []
        for backup in backups:
            result.append({
                'filename': backup.name,
                'path': str(backup),
                'size': backup.stat().st_size,
                'created': datetime.fromtimestamp(backup.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return result
    
    def restore_backup(self, backup_filename: str):
        """恢复备份"""
        backup_file = self.backup_dir / backup_filename
        
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup not found: {backup_filename}")
        
        # 先备份当前配置
        self._backup()
        
        # 恢复
        shutil.copy(backup_file, self.config_path)
        return True
    
    # ========== 显示 ==========
    
    def show_status(self):
        """显示完整状态"""
        print("\n╔══════════════════════════════════════╗")
        print("║  ClawAPI Config Manager              ║")
        print("╚══════════════════════════════════════╝")
        
        # Primary & Fallbacks
        print(f"\n  Primary: {self.get_primary_model()}")
        print("\n  Fallback chain:")
        for i, fb in enumerate(self.get_fallbacks(), 1):
            print(f"    {i}. {fb}")
        
        # Providers
        print("\n  Providers:")
        for provider in self.list_providers():
            print(f"    • {provider['name']}: {provider['model_count']} models")
        
        # Validation
        validation = self.validate_config()
        if validation['valid']:
            print("\n  ✅ Configuration valid")
        else:
            print("\n  ⚠️  Issues found:")
            for issue in validation['issues']:
                print(f"    - {issue}")
        
        print()


def main():
    """CLI 入口"""
    import sys
    
    if len(sys.argv) < 2:
        print("\n🔧 ClawAPI Config Manager")
        print("\nProvider Management:")
        print("  list-providers              List all providers")
        print("  add-provider <name> <url> <key>")
        print("  remove-provider <name>")
        print("  update-key <provider> <new_key>")
        print("\nModel Management:")
        print("  list-models [provider]      List models")
        print("  add-model <provider> <id> <name>")
        print("  remove-model <provider> <id>")
        print("\nPrimary & Fallback:")
        print("  get-primary                 Show primary model")
        print("  set-primary <model_id>")
        print("  get-fallbacks               Show fallback chain")
        print("  add-fallback <model_id>")
        print("  remove-fallback <model_id>")
        print("\nTesting:")
        print("  test <provider>             Test provider connection")
        print("  validate                    Validate configuration")
        print("\nBackup:")
        print("  list-backups                List all backups")
        print("  restore <filename>          Restore from backup")
        print("\nStatus:")
        print("  status                      Show full status")
        return
    
    manager = ClawAPIConfigManager()
    cmd = sys.argv[1]
    
    try:
        if cmd == 'list-providers':
            for p in manager.list_providers():
                print(f"{p['name']}: {p['model_count']} models, key: {p['api_key']}")
        
        elif cmd == 'add-provider':
            name, url, key = sys.argv[2], sys.argv[3], sys.argv[4]
            manager.add_provider(name, url, key)
            print(f"✅ Provider '{name}' added")
        
        elif cmd == 'remove-provider':
            manager.remove_provider(sys.argv[2])
            print(f"✅ Provider removed")
        
        elif cmd == 'update-key':
            provider, key = sys.argv[2], sys.argv[3]
            manager.update_api_key(provider, key)
            print(f"✅ API key updated")
        
        elif cmd == 'list-models':
            provider = sys.argv[2] if len(sys.argv) > 2 else None
            for m in manager.list_models(provider):
                print(f"{m['full_id']}: {m['name']}")
        
        elif cmd == 'add-model':
            provider, model_id, name = sys.argv[2], sys.argv[3], sys.argv[4]
            manager.add_model(provider, model_id, name)
            print(f"✅ Model added")
        
        elif cmd == 'remove-model':
            provider, model_id = sys.argv[2], sys.argv[3]
            manager.remove_model(provider, model_id)
            print(f"✅ Model removed")
        
        elif cmd == 'get-primary':
            print(manager.get_primary_model())
        
        elif cmd == 'set-primary':
            manager.set_primary_model(sys.argv[2])
            print(f"✅ Primary model set")
        
        elif cmd == 'get-fallbacks':
            for fb in manager.get_fallbacks():
                print(fb)
        
        elif cmd == 'add-fallback':
            manager.add_fallback(sys.argv[2])
            print(f"✅ Fallback added")
        
        elif cmd == 'remove-fallback':
            manager.remove_fallback(sys.argv[2])
            print(f"✅ Fallback removed")
        
        elif cmd == 'test':
            result = manager.test_provider(sys.argv[2])
            if result['success']:
                print(f"✅ Provider OK")
            else:
                print(f"❌ Failed: {result.get('error', result.get('message'))}")
        
        elif cmd == 'validate':
            result = manager.validate_config()
            if result['valid']:
                print("✅ Configuration valid")
            else:
                print("⚠️  Issues:")
                for issue in result['issues']:
                    print(f"  - {issue}")
        
        elif cmd == 'list-backups':
            for backup in manager.list_backups():
                print(f"{backup['filename']}: {backup['created']}")
        
        elif cmd == 'restore':
            manager.restore_backup(sys.argv[2])
            print(f"✅ Backup restored")
        
        elif cmd == 'status':
            manager.show_status()
        
        else:
            print(f"❌ Unknown command: {cmd}")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
