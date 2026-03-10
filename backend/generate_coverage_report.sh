#!/bin/bash

# generate_coverage_report.sh
# Script per generare report coverage professionale per tesi

set -e

echo "🎓 Meeting Intelligence - Coverage Report Generator per Tesi"
echo "============================================================="
echo ""

# Colori
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_DIR="coverage_reports/${TIMESTAMP}"

echo -e "${BLUE}📊 Generazione report coverage...${NC}"
echo ""

# 1. Run test con coverage
echo -e "${YELLOW}Step 1: Esecuzione test suite completa...${NC}"
pytest --cov --cov-report=html --cov-report=xml --cov-report=term-missing --junitxml=junit.xml

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo -e "${RED}❌ Alcuni test sono falliti!${NC}"
    echo "   Fix i test prima di generare il report finale."
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Test completati con successo!${NC}"
echo ""

# 2. Crea directory report
echo -e "${YELLOW}Step 2: Organizzazione report...${NC}"
mkdir -p "$REPORT_DIR"

# 3. Copia report HTML
cp -r htmlcov/* "$REPORT_DIR/"
cp coverage.xml "$REPORT_DIR/"
cp junit.xml "$REPORT_DIR/"

# 4. Genera summary
echo -e "${YELLOW}Step 3: Generazione summary...${NC}"

cat > "$REPORT_DIR/COVERAGE_SUMMARY.txt" << 'EOF'
================================================================
MEETING INTELLIGENCE - COVERAGE REPORT SUMMARY
================================================================

Generato: $(date)
Python Version: $(python --version)
PyTest Version: $(pytest --version | head -1)

----------------------------------------------------------------
METRICHE GLOBALI
----------------------------------------------------------------

$(pytest --cov --cov-report=term-missing 2>&1 | grep -A 10 "coverage:" || echo "Dati non disponibili")

----------------------------------------------------------------
TEST EXECUTION SUMMARY
----------------------------------------------------------------

$(pytest --tb=no -v 2>&1 | tail -5 || echo "Dati non disponibili")

----------------------------------------------------------------
FILE GENERATI
----------------------------------------------------------------

1. index.html          - Report HTML interattivo (apri in browser)
2. coverage.xml        - Report XML (per CI/CD)
3. junit.xml           - JUnit XML (per Jenkins/GitLab)
4. COVERAGE_SUMMARY.txt - Questo file

----------------------------------------------------------------
UTILIZZO PER TESI
----------------------------------------------------------------

**Capitolo Implementazione:**
- Screenshot di index.html
- Tabella coverage per file
- Grafico evoluzione coverage

**Capitolo Validazione:**
- Metriche numeriche da questo file
- Evidenza empirica qualità software

**Appendice:**
- Report completo HTML allegato

----------------------------------------------------------------
NEXT STEPS
----------------------------------------------------------------

1. Apri index.html nel browser
2. Fai screenshot delle pagine principali
3. Estrai metriche per tabelle tesi
4. Allega report completo in appendice

================================================================
EOF

# 5. Genera badge coverage
COVERAGE=$(pytest --cov 2>&1 | grep "TOTAL" | awk '{print $NF}' | sed 's/%//')

if [ -n "$COVERAGE" ]; then
    echo -e "${GREEN}Coverage: ${COVERAGE}%${NC}"
    
    # Badge colore
    if (( $(echo "$COVERAGE >= 90" | bc -l) )); then
        BADGE_COLOR="brightgreen"
        STATUS="✅ Excellent"
    elif (( $(echo "$COVERAGE >= 80" | bc -l) )); then
        BADGE_COLOR="green"
        STATUS="✅ Good"
    elif (( $(echo "$COVERAGE >= 70" | bc -l) )); then
        BADGE_COLOR="yellow"
        STATUS="⚠️  Fair"
    else
        BADGE_COLOR="red"
        STATUS="❌ Needs Improvement"
    fi
    
    echo "Status: $STATUS"
fi

echo ""

# 6. Crea README nel report
cat > "$REPORT_DIR/README.md" << EOF
# 📊 Coverage Report - Meeting Intelligence

**Data Generazione**: $(date)  
**Coverage Globale**: ${COVERAGE}%  
**Status**: $STATUS

---

## 📁 File Inclusi

| File | Descrizione | Uso |
|------|-------------|-----|
| **index.html** | Report HTML interattivo | Apri in browser per visualizzazione completa |
| **coverage.xml** | Report XML | Per tool CI/CD (Jenkins, GitLab) |
| **junit.xml** | JUnit XML | Per report test execution |
| **COVERAGE_SUMMARY.txt** | Summary testuale | Per inclusione diretta in documenti |

---

## 🎓 Utilizzo per Tesi

### Capitolo: Implementazione
1. Screenshot della pagina principale (index.html)
2. Tabella coverage per modulo
3. Grafico a barre coverage

### Capitolo: Validazione
1. Metriche numeriche da COVERAGE_SUMMARY.txt
2. Tabella evoluzione coverage nel tempo
3. Confronto con standard industriali

### Appendice
1. Allegare report HTML completo
2. Include screenshot significativi
3. Documentazione metodologia (vedi METODOLOGIA_TESTING_TESI.md)

---

## 📊 Come Aprire il Report

### Windows
\`\`\`
start index.html
\`\`\`

### Mac
\`\`\`
open index.html
\`\`\`

### Linux
\`\`\`
xdg-open index.html
\`\`\`

---

## 📈 Interpretazione Metriche

### Coverage Percentuale
- **>90%**: ✅ Eccellente - Standard industriale professionale
- **80-90%**: ✅ Buono - Accettabile per produzione
- **70-80%**: ⚠️  Sufficiente - Migliorabile
- **<70%**: ❌ Insufficiente - Richiede più test

### Righe Coverage
- **Verde**: Righe eseguite durante i test
- **Rosso**: Righe MAI eseguite (mancante coverage)
- **Giallo**: Branch parzialmente testati

---

## 🔍 Analisi Dettagliata

Per analisi dettagliata:
1. Apri \`index.html\` in browser
2. Click su nome file per dettagli
3. Vedi righe esatte non coperte
4. Aggiungi test per righe rosse

---

**Generato da**: generate_coverage_report.sh  
**Progetto**: Meeting Intelligence  
**Versione**: 1.0.0
EOF

# 7. Final summary
echo ""
echo -e "${GREEN}================================================================${NC}"
echo -e "${GREEN}✅ REPORT COVERAGE GENERATO CON SUCCESSO!${NC}"
echo -e "${GREEN}================================================================${NC}"
echo ""
echo "📁 Report salvato in: $REPORT_DIR"
echo ""
echo "📄 File disponibili:"
echo "   - index.html (apri in browser)"
echo "   - coverage.xml (per CI/CD)"
echo "   - junit.xml (test execution)"
echo "   - COVERAGE_SUMMARY.txt (summary)"
echo "   - README.md (guida utilizzo)"
echo ""
echo -e "${BLUE}📊 Metriche Principali:${NC}"
echo "   Coverage: ${COVERAGE}%"
echo "   Status: $STATUS"
echo ""
echo -e "${YELLOW}🎓 Per la tesi:${NC}"
echo "   1. Apri index.html per screenshot"
echo "   2. Usa COVERAGE_SUMMARY.txt per metriche"
echo "   3. Allega report completo in appendice"
echo ""
echo -e "${GREEN}Next: Apri il report!${NC}"
echo "   \$ open $REPORT_DIR/index.html"
echo ""

exit 0