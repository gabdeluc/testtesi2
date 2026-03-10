FROM node:20-alpine

WORKDIR /app

# Copia i file di configurazione delle dipendenze
COPY package*.json ./

# Installa le dipendenze
RUN npm install

# Copia il resto del codice sorgente
COPY . .

# Esponi la porta 3000
EXPOSE 3000

# Comando per avviare l'applicazione in modalità sviluppo
CMD ["npm", "run", "dev"]