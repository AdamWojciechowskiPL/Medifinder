@echo off
:: ============================================================================
:: :: Uruchamia aplikacje Medicover Finder w srodowisku wirtualnym
:: :: Wersja zalecana - bezposrednie wywolanie interpretera.
:: ============================================================================

:: Bezposrednio uruchamiamy interpreter pythonw.exe z folderu venv,
:: podajac mu nasz skrypt run.py jako argument.
:: To gwarantuje, ze zawsze zostanie uzyte wlasciwe srodowisko,
:: bez potrzeby aktywacji.

start /B "Medicover App" "venv\Scripts\pythonw.exe" "run.py"
