# Push To GitHub Wiki

This staging folder was generated locally because the live wiki repository could not be cloned from this environment.

## HTTPS flow

```bash
git clone https://github.com/MN755/Codex-Mission_Control.wiki.git
cd Codex-Mission_Control.wiki
cp /path/to/wiki-staging/*.md .
git status
git add .
git commit -m "Add Mission Control headless documentation wiki"
git push origin master
```

## SSH flow

```bash
git clone git@github.com:MN755/Codex-Mission_Control.wiki.git
cd Codex-Mission_Control.wiki
cp /path/to/wiki-staging/*.md .
git status
git add .
git commit -m "Add Mission Control headless documentation wiki"
git push origin master
```

## Windows PowerShell copy example

```powershell
git clone https://github.com/MN755/Codex-Mission_Control.wiki.git
Set-Location .\Codex-Mission_Control.wiki
Copy-Item ..\wiki-staging\*.md .
git status
git add .
git commit -m "Add Mission Control headless documentation wiki"
git push origin master
```
