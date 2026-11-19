"""Roda em sequência os dois robôs pesados das bancadas (Receita e TSE pela cópia no R2):
bancadas_receita.py (atividade secundária, participações, CNPJs dos bens, doações) e bancadas_familiares.py
(familiares e terceiros). Usar depois de criar ou mudar uma bancada em bancadas-regras.json."""
import subprocess, sys, os, shutil
aqui = os.path.dirname(os.path.abspath(__file__))
for s in ('bancadas_receita.py', 'bancadas_familiares.py'):
    print('==', s, flush=True)
    r = subprocess.run([sys.executable, os.path.join(aqui, s)])
    if os.path.exists('saida/resumo.json'): shutil.move('saida/resumo.json', f"saida/resumo_{s.replace('.py', '')}.json")
    if r.returncode: sys.exit(r.returncode)
