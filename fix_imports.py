import os
import re

# Lista plików do naprawy
app_modules = [
    'appointment_formatter', 'chrome_driver_factory', 'config', 
    'custom_widgets', 'data_manager', 'discover_specialties', 
    'error_handler', 'gui', 'login_form_handler', 'main', 
    'medicover_api', 'medicover_authenticator', 'medicover_client', 
    'profile_manager'
]

# Wzorzec do znalezienia absolute imports
pattern = r'^from (' + '|'.join(app_modules) + r') import'

app_dir = 'app'
for filename in os.listdir(app_dir):
    if filename.endswith('.py') and filename != '__init__.py':
        filepath = os.path.join(app_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Zamień absolute imports na relative
        new_content = re.sub(pattern, r'from .\1 import', content, flags=re.MULTILINE)
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'✅ Fixed: {filename}')
        else:
            print(f'⏭️  Skip: {filename}')

print('\n🎉 Done! Now commit and push.')
