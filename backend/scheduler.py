"""
Backend Scheduler for Medifinder
Manages background tasks for cyclic appointment checking and auto-booking
"""
import logging
import json
import threading
import time
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

logger = logging.getLogger(__name__)

class MedifinderScheduler:
    """
    Zarządza zadaniami w tle (background jobs) dla aplikacji Medifinder.
    Każdy użytkownik może mieć własne zadanie cyklicznego sprawdzania.
    """
    
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
        """Wczytuje zapisane zadania z pliku przy starcie aplikacji."""
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
        """Zapisuje aktualne zadania do pliku."""
        try:
            with open(self.tasks_config_file, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False, default=str)
            logger.debug("Zadania zapisane do pliku")
        except Exception as e:
            logger.error(f"Błąd zapisu zadań: {e}")

    def _sync_tasks_from_file(self):
        """Odświeża stan zadań z pliku (synchronizacja między workerami)."""
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
                            try: self.scheduler.remove_job(tid)
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
    
    def _execute_task(self, task_id: str):
        # --- JITTER LOGIC START ---
        delay = random.uniform(1, 15)
        pre_task_data = self.tasks.get(task_id)
        if pre_task_data and pre_task_data.get('twin_profile') and str(pre_task_data.get('profile', '')).endswith('9'): 
             delay += 10
        logger.info(f"⏳ [Profile {task_id}] Oczekiwanie {delay:.2f}s przed startem (Jitter)...")
        time.sleep(delay)
        # --- JITTER LOGIC END ---

        self._sync_tasks_from_file()
        if task_id not in self.tasks: return
        task_data = self.tasks[task_id]
        if not task_data.get('active', False):
            try: self.scheduler.remove_job(task_id)
            except: pass
            return

        # --- SMART BACKOFF CHECK (COOLDOWN) ---
        cooldown_until_str = task_data.get('cooldown_until')
        if cooldown_until_str:
            try:
                cooldown_until = datetime.fromisoformat(cooldown_until_str)
                if datetime.now() < cooldown_until:
                    logger.warning(f"❄️ [{task_id}] Zadanie w trybie COOLDOWN do {cooldown_until.strftime('%H:%M:%S')} (po błędzie 429). Pomijam.")
                    return # Skip execution
                else:
                    # Cooldown ended
                    logger.info(f"🔥 [{task_id}] Koniec COOLDOWN. Wznawiam sprawdzanie.")
                    self.tasks[task_id]['cooldown_until'] = None # Clear it
            except ValueError:
                self.tasks[task_id]['cooldown_until'] = None

        user_email = task_data['user_email']
        profile = task_data['profile']
        search_params = task_data['search_params']
        auto_book = task_data.get('auto_book', False)
        
        # --- AUTO STOP CHECK (24h) ---
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
            except ValueError:
                pass 

        # --- NEW: Twin Booking Params ---
        twin_profile = task_data.get('twin_profile')
        is_twin_mode = bool(twin_profile)
        
        logger.info(f"🔍 [{task_id}] Rozpoczynam sprawdzanie (Twin Mode: {is_twin_mode})...")
        
        try:
            now = datetime.now()
            self.tasks[task_id]['last_run'] = now.isoformat()
            self._save_tasks()
            
            results = self.med_app.search_appointments(
                user_email=user_email,
                profile=profile,
                **search_params
            )
            
            # --- LOGIC BRANCHING ---
            appointments_to_process = results
            pairs = []
            
            if is_twin_mode and results:
                # W trybie bliźniaczym szukamy PAR wizyt
                pairs = self.med_app.find_consecutive_slots(results)
                logger.info(f"📊 [{task_id}] Znaleziono {len(results)} wizyt, w tym {len(pairs)} par(y) dla bliźniaków")
                self.tasks[task_id]['last_results'] = {
                    'timestamp': datetime.now().isoformat(),
                    'count': len(results),
                    'pairs_count': len(pairs),
                    'appointments': results[:50]
                }
            else:
                # Standardowy tryb
                logger.info(f"📊 [{task_id}] Znaleziono {len(results)} wizyt")
                self.tasks[task_id]['last_results'] = {
                    'timestamp': datetime.now().isoformat(),
                    'count': len(results),
                    'appointments': results[:50]
                }

            # --- AUTO BOOKING LOGIC ---
            if auto_book:
                if is_twin_mode:
                    if pairs:
                        pair = pairs[0] # Bierzemy pierwszą parę
                        apt1, apt2 = pair
                        logger.info(f"🎯 [{task_id}] TWIN-BOOKING: Próba rezerwacji pary wizyt...")
                        
                        # 1. Rezerwacja dla profilu głównego (Lider)
                        res1 = self.med_app.book_appointment(
                            user_email=user_email,
                            profile=profile,
                            appointment_id=apt1.get('appointmentId'),
                            booking_string=apt1.get('bookingString')
                        )
                        
                        success1 = res1.get('success')
                        success2 = False
                        msg2 = "Skipped"

                        # 2. Rezerwacja dla profilu drugiego (Twin), jeśli pierwsza się udała
                        if success1:
                            logger.info(f"✅ [{task_id}] Pierwsza wizyta OK. Przełączam na profil {twin_profile}...")
                            res2 = self.med_app.book_appointment(
                                user_email=user_email,
                                profile=twin_profile,
                                appointment_id=apt2.get('appointmentId'),
                                booking_string=apt2.get('bookingString')
                            )
                            success2 = res2.get('success')
                            msg2 = res2.get('message')
                        
                        if success1 and success2:
                            logger.info(f"✅✅ [{task_id}] PEŁNY SUKCES! Zatrzymuję zadanie.")
                            self.stop_task(user_email, profile)
                            self.tasks[task_id]['last_booking'] = {
                                'timestamp': datetime.now().isoformat(),
                                'mode': 'twin',
                                'success': True,
                                'details': f"Booked for {profile} and {twin_profile}"
                            }
                        else:
                            logger.warning(f"⚠️ [{task_id}] Twin booking partial fail. 1: {success1}, 2: {success2} ({msg2})")
                            self.tasks[task_id]['last_booking_attempt'] = {
                                'timestamp': datetime.now().isoformat(),
                                'success': False,
                                'error': f"Partial fail. 1:{success1}, 2:{msg2}"
                            }
                    else:
                        logger.info(f"ℹ️ [{task_id}] Brak par wizyt. Czekam dalej.")

                elif results: 
                    # Standard auto-book logic
                    first = results[0]
                    res = self.med_app.book_appointment(
                        user_email=user_email, 
                        profile=profile, 
                        appointment_id=first.get('appointmentId'), 
                        booking_string=first.get('bookingString')
                    )
                    if res.get('success'):
                        self.stop_task(user_email, profile)
                        self.tasks[task_id]['last_booking'] = {'timestamp': datetime.now().isoformat(), 'success': True}
                        self._save_tasks()
                        return
            
            # Update next run
            interval = task_data.get('interval_minutes', 5)
            self.tasks[task_id]['next_run'] = (datetime.now() + timedelta(minutes=interval)).isoformat()
            self.tasks[task_id]['runs_count'] = task_data.get('runs_count', 0) + 1
            self._save_tasks()
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"❌ [{task_id}] Błąd: {error_str}", exc_info=True)
            self.tasks[task_id]['last_error'] = {'timestamp': datetime.now().isoformat(), 'error': error_str}
            
            # --- SMART BACKOFF (429 handling) ---
            if "429" in error_str or "Rate limit" in error_str or "RateLimitException" in error_str:
                cooldown_minutes = 20
                cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
                self.tasks[task_id]['cooldown_until'] = cooldown_until.isoformat()
                logger.warning(f"⛔️ [{task_id}] WYKRYTO TWARDĄ BLOKADĘ (429). Pauza do {cooldown_until.strftime('%H:%M:%S')} ({cooldown_minutes} min).")
            
            self._save_tasks()
    
    def start_task(self, user_email: str, profile: str, search_params: Dict[str, Any], 
                   interval_minutes: int = 5, auto_book: bool = False, twin_profile: str = None) -> Dict[str, Any]:
        """Uruchamia nowe zadanie cyklicznego sprawdzania."""
        
        # --- UPDATED LIMIT CHECK (3 tasks per user) ---
        user_tasks = self.get_all_user_tasks(user_email)
        target_task_id = self._generate_task_id(user_email, profile)
        
        # Count active tasks for this user (excluding the current one if it exists)
        active_count = sum(1 for tid, data in user_tasks.items() 
                          if data.get('active', False) and tid != target_task_id)
        
        if active_count >= 3:
            return {
                'success': False, 
                'error': 'Limit zadań osiągnięty. Możesz mieć maksymalnie 3 aktywne automaty. Zatrzymaj inne zadania.'
            }
        # -----------------------------------------

        task_id = self._generate_task_id(user_email, profile)
        
        now_dt = datetime.now()
        expires_at = now_dt + timedelta(hours=24) # Auto-stop po 24h

        task_data = {
            'user_email': user_email,
            'profile': profile,
            'twin_profile': twin_profile, 
            'search_params': search_params,
            'interval_minutes': interval_minutes,
            'auto_book': auto_book,
            'active': True,
            'created_at': now_dt.isoformat(),
            'expires_at': expires_at.isoformat(), # Zapisujemy czas wygaśnięcia
            'runs_count': 0,
            'cooldown_until': None # Reset cooldown on new start
        }
        
        self.tasks[task_id] = task_data
        self._schedule_task(task_id, task_data)
        self._save_tasks()
        
        msg = f'Zadanie uruchomione (co {interval_minutes} min)'
        if twin_profile:
            msg += f" [Tryb Bliźniak: {twin_profile}]"

        return {
            'success': True,
            'message': msg,
            'task_id': task_id,
            'next_run': task_data.get('next_run'),
            'expires_at': expires_at.isoformat()
        }
    
    def stop_task(self, user_email: str, profile: str) -> Dict[str, Any]:
        task_id = self._generate_task_id(user_email, profile)
        if task_id not in self.tasks:
            self._sync_tasks_from_file()
            if task_id not in self.tasks: return {'success': False, 'message': 'Zadanie nie istnieje'}
        
        try: self.scheduler.remove_job(task_id)
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