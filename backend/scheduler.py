import logging
import json
import threading
import time
import random
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

logger = logging.getLogger(__name__)

class MedifinderScheduler:
    def __init__(self, config_dir: Path, med_app):
        self.config_dir = config_dir
        self.med_app = med_app
        self.scheduler = BackgroundScheduler(daemon=True)
        self.tasks_config_file = config_dir / "scheduler_tasks.json"
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._load_tasks()
        self.scheduler.start()
        logger.info("🚀 Medifinder Scheduler uruchomiony")
        
    def _load_tasks(self):
        try:
            if self.tasks_config_file.exists():
                with open(self.tasks_config_file, 'r', encoding='utf-8') as f:
                    self.tasks = json.load(f)
                logger.info(f"Wczytano {len(self.tasks)} zadań z pliku konfiguracyjnego")
                for task_id, task_data in self.tasks.items():
                    if task_data.get('active', False):
                        self._schedule_task(task_id, task_data)
            else:
                logger.info("Brak zapisanych zadań - tworzenie nowego pliku")
                self.tasks = {}
        except Exception as e:
            logger.error(f"Błąd wczytywania zadań: {e}")
            self.tasks = {}
    
    def _save_tasks(self):
        try:
            with open(self.tasks_config_file, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False, default=str)
            logger.debug("Zadania zapisane do pliku")
        except Exception as e:
            logger.error(f"Błąd zapisu zadań: {e}")

    def _sync_tasks_from_file(self):
        try:
            if self.tasks_config_file.exists():
                with open(self.tasks_config_file, 'r', encoding='utf-8') as f:
                    saved_tasks = json.load(f)
                    for tid, data in saved_tasks.items():
                        self.tasks[tid] = data
                    current_ids = set(self.tasks.keys())
                    saved_ids = set(saved_tasks.keys())
                    for tid in current_ids - saved_ids:
                        if tid in self.tasks:
                            del self.tasks[tid]
                            try: 
                                self.scheduler.remove_job(tid)
                                self.scheduler.remove_job(f"{tid}_warmup")
                            except: pass
        except Exception: pass
    
    def _ensure_job_running(self, task_id: str):
        if task_id not in self.tasks: return
        task_data = self.tasks[task_id]
        if not task_data.get('active', False): return
        current_job = self.scheduler.get_job(task_id)
        if not current_job:
            logger.warning(f"⚠️ Zadanie {task_id} jest aktywne w pliku, ale brak go w schedulerze. Przywracam...")
            self._schedule_task(task_id, task_data)
    
    def _generate_task_id(self, user_email: str, profile: str) -> str:
        return f"{user_email}::{profile}"
    
    def _schedule_task(self, task_id: str, task_data: Dict[str, Any]):
        try:
            mode = task_data.get('mode', 'interval')
            
            if mode == 'midnight':
                # --- MIDNIGHT SNIPER MODE ---
                # 1. Warm-up Job (23:55)
                warmup_id = f"{task_id}_warmup"
                self.scheduler.add_job(
                    func=self._execute_warmup,
                    trigger=CronTrigger(hour=23, minute=55),
                    id=warmup_id,
                    args=[task_id],
                    replace_existing=True,
                    max_instances=1
                )
                
                # 2. Burst Job (00:00 - 00:05, every minute)
                # minute='0-5' means 0,1,2,3,4,5
                self.scheduler.add_job(
                    func=self._execute_task,
                    trigger=CronTrigger(hour=0, minute='0-5', second=1), 
                    id=task_id,
                    args=[task_id],
                    replace_existing=True,
                    max_instances=1
                )
                
                logger.info(f"✅ Zadanie {task_id} zaplanowane w trybie SNIPER (Warmup 23:55, Strzał 00:00-00:05)")
                
                # Estimate next run for display
                now = datetime.now()
                if now.hour == 23 and now.minute >= 55:
                    # Warmup done/pending, waiting for midnight
                    next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=1)
                elif now.hour == 0 and now.minute <= 5:
                    # Currently running
                    next_run = now + timedelta(minutes=1)
                else:
                    # Waiting for next warmup/run
                    next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=1)
                    if now.hour < 23 or (now.hour == 23 and now.minute < 55):
                        next_run = now.replace(hour=23, minute=55, second=0)

                if 'next_run' not in self.tasks[task_id]:
                    self.tasks[task_id]['next_run'] = next_run.isoformat()
                
            else:
                # --- STANDARD INTERVAL MODE ---
                interval_minutes = task_data.get('interval_minutes', 5)
                self.scheduler.add_job(
                    func=self._execute_task,
                    trigger=IntervalTrigger(minutes=interval_minutes),
                    id=task_id,
                    args=[task_id],
                    replace_existing=True,
                    max_instances=1
                )
                if 'next_run' not in self.tasks[task_id]:
                    self.tasks[task_id]['next_run'] = (datetime.now() + timedelta(minutes=interval_minutes)).isoformat()
                logger.info(f"✅ Zadanie {task_id} zaplanowane (co {interval_minutes} min)")
                
        except Exception as e:
            logger.error(f"Błąd planowania zadania {task_id}: {e}")

    def _execute_warmup(self, task_id: str):
        """Warm-up session before midnight."""
        self._sync_tasks_from_file()
        if task_id not in self.tasks: return
        t_data = self.tasks[task_id]
        if not t_data.get('active', False): return

        logger.info(f"🔥 [{task_id}] SNIPER WARM-UP (23:55): Odświeżanie tokenów...")
        try:
            self.med_app.refresh_session(t_data['user_email'], t_data['profile'])
            if t_data.get('twin_profile'):
                self.med_app.refresh_session(t_data['user_email'], t_data['twin_profile'])
        except Exception as e:
            logger.error(f"⚠️ [{task_id}] Warm-up failed: {e}")

    def _execute_task(self, task_id: str):
        self._sync_tasks_from_file()
        if task_id not in self.tasks: return
        
        task_data = self.tasks[task_id]
        if not task_data.get('active', False):
            try: 
                self.scheduler.remove_job(task_id)
                self.scheduler.remove_job(f"{task_id}_warmup")
            except: pass
            return

        mode = task_data.get('mode', 'interval')
        user_email = task_data['user_email']
        profile = task_data['profile']
        search_params = task_data['search_params']
        
        # --- JITTER (Only for interval mode) ---
        if mode == 'interval':
            delay = random.uniform(1, 15)
            # Extra delay for twin profiles ending in 9 (legacy logic preserved)
            if task_data.get('twin_profile') and str(profile).endswith('9'): 
                 delay += 10
            logger.info(f"⏳ [{task_id}] Oczekiwanie {delay:.2f}s (Jitter)...")
            time.sleep(delay)
            self._sync_tasks_from_file()
            # Re-check active after sleep
            if task_id not in self.tasks or not self.tasks[task_id].get('active', False): return

        # --- SMART BACKOFF CHECK (COOLDOWN) ---
        cooldown_until_str = task_data.get('cooldown_until')
        if cooldown_until_str:
            try:
                cooldown_until = datetime.fromisoformat(cooldown_until_str)
                if datetime.now() < cooldown_until:
                    logger.warning(f"❄️ [{task_id}] Zadanie w trybie COOLDOWN do {cooldown_until.strftime('%H:%M:%S')}. Pomijam.")
                    return 
                else:
                    logger.info(f"🔥 [{task_id}] Koniec COOLDOWN. Wznawiam sprawdzanie.")
                    self.tasks[task_id]['cooldown_until'] = None
            except ValueError:
                self.tasks[task_id]['cooldown_until'] = None

        # --- AUTO STOP CHECKS ---
        # 1. 24h Timeout (Only for Interval Mode)
        if mode == 'interval':
            expires_at_str = task_data.get('expires_at')
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.now() > expires_at:
                        logger.info(f"🛑 [{task_id}] Czas działania (24h) minął. Zatrzymuję zadanie.")
                        self.stop_task(user_email, profile)
                        self.tasks[task_id]['stop_reason'] = "Timeout 24h"
                        self._save_tasks()
                        return
                except ValueError: pass 
        
        # 2. Date Limit (For Midnight Mode)
        if mode == 'midnight':
            end_date_str = search_params.get('end_date')
            if end_date_str:
                try:
                    # Usually "YYYY-MM-DD", but handle ISO
                    d_str = end_date_str.split('T')[0]
                    end_date_obj = date.fromisoformat(d_str)
                    
                    # If we passed the end date (search is for dates UP TO end_date)
                    # Actually, if we are checking ON end_date, we should still run.
                    # Stop if today > end_date.
                    if datetime.now().date() > end_date_obj:
                         logger.info(f"🛑 [{task_id}] Minęła data końcowa filtra ({end_date_str}). Zatrzymuję Snipera.")
                         self.stop_task(user_email, profile)
                         self.tasks[task_id]['stop_reason'] = "Date Limit Reached"
                         self._save_tasks()
                         return
                except Exception as e:
                    logger.warning(f"⚠️ [{task_id}] Błąd sprawdzania daty końcowej: {e}")

        # --- EXECUTION ---
        twin_profile = task_data.get('twin_profile')
        is_twin_mode = bool(twin_profile)
        auto_book = task_data.get('auto_book', False)
        
        logger.info(f"🔍 [{task_id}] Start (Mode: {mode}, Twin: {is_twin_mode})...")
        
        try:
            now = datetime.now()
            self.tasks[task_id]['last_run'] = now.isoformat()
            self._save_tasks()
            
            results = self.med_app.search_appointments(
                user_email=user_email,
                profile=profile,
                **search_params
            )
            
            pairs = []
            if is_twin_mode and results:
                pairs = self.med_app.find_consecutive_slots(results)
                self.tasks[task_id]['last_results'] = {
                    'timestamp': datetime.now().isoformat(),
                    'count': len(results),
                    'pairs_count': len(pairs),
                    'appointments': results[:50]
                }
            else:
                self.tasks[task_id]['last_results'] = {
                    'timestamp': datetime.now().isoformat(),
                    'count': len(results),
                    'appointments': results[:50]
                }
            
            logger.info(f"📊 [{task_id}] Wyniki: {len(results)} (Pary: {len(pairs)})")

            # --- AUTO BOOKING ---
            if auto_book:
                if is_twin_mode:
                    if pairs:
                        pair = pairs[0]
                        apt1, apt2 = pair
                        logger.info(f"🎯 [{task_id}] TWIN-BOOKING: Próba rezerwacji...")
                        
                        res1 = self.med_app.book_appointment(user_email, profile, apt1.get('appointmentId'), apt1.get('bookingString'))
                        success1 = res1.get('success')
                        
                        if success1:
                            res2 = self.med_app.book_appointment(user_email, twin_profile, apt2.get('appointmentId'), apt2.get('bookingString'))
                            success2 = res2.get('success')
                            
                            if success2:
                                logger.info(f"✅✅ [{task_id}] PEŁNY SUKCES! Zatrzymuję zadanie.")
                                self.stop_task(user_email, profile)
                                self.tasks[task_id]['last_booking'] = {'timestamp': datetime.now().isoformat(), 'mode': 'twin', 'success': True}
                            else:
                                logger.warning(f"⚠️ [{task_id}] Twin booking partial fail.")
                        else:
                            logger.warning(f"⚠️ [{task_id}] First booking failed.")
                elif results:
                    first = results[0]
                    res = self.med_app.book_appointment(user_email, profile, first.get('appointmentId'), first.get('bookingString'))
                    if res.get('success'):
                        logger.info(f"✅ [{task_id}] SUKCES! Zatrzymuję zadanie.")
                        self.stop_task(user_email, profile)
                        self.tasks[task_id]['last_booking'] = {'timestamp': datetime.now().isoformat(), 'success': True}
                        self._save_tasks()
                        return

            # --- UPDATE NEXT RUN ---
            if mode == 'interval':
                interval = task_data.get('interval_minutes', 5)
                self.tasks[task_id]['next_run'] = (datetime.now() + timedelta(minutes=interval)).isoformat()
            else:
                # Midnight mode next run logic for display
                now = datetime.now()
                if now.hour == 0 and now.minute < 5:
                     self.tasks[task_id]['next_run'] = (now + timedelta(minutes=1)).isoformat()
                else:
                     self.tasks[task_id]['next_run'] = (now.replace(hour=0, minute=0, second=1) + timedelta(days=1)).isoformat()

            self.tasks[task_id]['runs_count'] = task_data.get('runs_count', 0) + 1
            self._save_tasks()
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"❌ [{task_id}] Błąd: {error_str}", exc_info=True)
            self.tasks[task_id]['last_error'] = {'timestamp': datetime.now().isoformat(), 'error': error_str}
            
            if "429" in error_str or "Rate limit" in error_str:
                cooldown_minutes = 20
                cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
                self.tasks[task_id]['cooldown_until'] = cooldown_until.isoformat()
                logger.warning(f"⛔️ [{task_id}] 429 DETECTED. Cooldown do {cooldown_until.strftime('%H:%M:%S')}")
            
            self._save_tasks()
    
    def start_task(self, user_email: str, profile: str, search_params: Dict[str, Any], mode: str = 'interval',
                   interval_minutes: int = 5, auto_book: bool = False, twin_profile: str = None) -> Dict[str, Any]:
        """Uruchamia nowe zadanie cyklicznego sprawdzania."""
        
        user_tasks = self.get_all_user_tasks(user_email)
        target_task_id = self._generate_task_id(user_email, profile)
        
        active_count = sum(1 for tid, data in user_tasks.items() 
                          if data.get('active', False) and tid != target_task_id)
        
        if active_count >= 3:
            return {'success': False, 'error': 'Limit zadań osiągnięty (max 3).'}

        task_id = self._generate_task_id(user_email, profile)
        now_dt = datetime.now()
        
        expires_at = None
        if mode == 'interval':
            expires_at = now_dt + timedelta(hours=24)

        task_data = {
            'user_email': user_email,
            'profile': profile,
            'mode': mode,
            'twin_profile': twin_profile, 
            'search_params': search_params,
            'interval_minutes': interval_minutes,
            'auto_book': auto_book,
            'active': True,
            'created_at': now_dt.isoformat(),
            'expires_at': expires_at.isoformat() if expires_at else None,
            'runs_count': 0,
            'cooldown_until': None 
        }
        
        self.tasks[task_id] = task_data
        self._schedule_task(task_id, task_data)
        self._save_tasks()
        
        msg = f'Zadanie uruchomione [{mode}]'
        if twin_profile: msg += f" [Twin: {twin_profile}]"

        return {
            'success': True,
            'message': msg,
            'task_id': task_id,
            'next_run': task_data.get('next_run'),
            'expires_at': task_data.get('expires_at')
        }
    
    def stop_task(self, user_email: str, profile: str) -> Dict[str, Any]:
        task_id = self._generate_task_id(user_email, profile)
        if task_id not in self.tasks:
            self._sync_tasks_from_file()
            if task_id not in self.tasks: return {'success': False, 'message': 'Zadanie nie istnieje'}
        
        try: 
            self.scheduler.remove_job(task_id)
        except JobLookupError: pass

        # Also remove warm-up job if exists
        try: 
            self.scheduler.remove_job(f"{task_id}_warmup")
        except JobLookupError: pass
        
        self.tasks[task_id]['active'] = False
        self.tasks[task_id]['stopped_at'] = datetime.now().isoformat()
        self._save_tasks()
        return {'success': True, 'message': 'Zadanie zatrzymane'}
    
    def get_task_status(self, user_email: str, profile: str) -> Optional[Dict[str, Any]]:
        self._sync_tasks_from_file()
        task_id = self._generate_task_id(user_email, profile)
        self._ensure_job_running(task_id)
        return self.tasks.get(task_id)
    
    def get_last_results(self, user_email: str, profile: str) -> Optional[Dict[str, Any]]:
        self._sync_tasks_from_file()
        task_id = self._generate_task_id(user_email, profile)
        return self.tasks.get(task_id, {}).get('last_results')
    
    def get_all_user_tasks(self, user_email: str) -> Dict[str, Dict[str, Any]]:
        self._sync_tasks_from_file()
        return {tid: data for tid, data in self.tasks.items() if data.get('user_email') == user_email}
    
    def shutdown(self):
        self.scheduler.shutdown(wait=True)
