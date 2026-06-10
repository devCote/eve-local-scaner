EVE Local Intel Scanner — Setup.exe build kit

Как собрать Setup.exe:

1. Скопируй эти 3 файла в корень проекта:
   - EVE Local Intel Scanner.spec
   - installer.iss
   - build_setup.bat

2. Убедись, что иконка лежит тут:
   assets\icons\app.ico

3. Установи Inno Setup 6 на Windows.

4. Запусти:
   build_setup.bat

5. Готовый установщик будет тут:
   installer_output\EVE_Local_Intel_Scanner_Setup.exe

Важно:
- Python на компьютере пользователя НЕ нужен.
- Установщик ставит PyInstaller-сборку с Python runtime внутри.
- data\ и killmails\ создаются установщиком как пустые папки.
- local_intel.sqlite и архивы killmails приложение создаст/докачает само при первом запуске.
- Пользователю нужен интернет при первом запуске, чтобы скачать последние 40 killmail архивов.

Почему не onefile:
QtWebEngine/Chromium стабильнее работает в onedir-сборке. Поэтому делается один Setup.exe, который устанавливает полноценную папку приложения.
