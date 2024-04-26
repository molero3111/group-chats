#!/bin/bash

# Function to initialize the database
initialize_database() {
    # Log in to PostgreSQL using the default user (postgres)
    psql -U postgres <<EOF
    \set AUTOCOMMIT off
    -- Create database
    CREATE DATABASE ${POSTGRES_DB};
    -- Create user with password
    CREATE USER ${POSTGRES_USER} WITH ENCRYPTED PASSWORD '${POSTGRES_PASSWORD}';
    -- Grant privileges to the user on the database
    GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB} TO ${POSTGRES_USER};
    -- Commit the transaction
    COMMIT;
EOF
}

# Run database initialization if not already done
if [[ -z "$(psql -U postgres -lqt | cut -d \| -f 1 | grep -w ${POSTGRES_DB})" ]]; then
    echo "Initializing database..."
    initialize_database
else
    echo "Database already initialized."
fi