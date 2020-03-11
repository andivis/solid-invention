import os
import sys
import sqlite3
import logging
import time
import random

from . import helpers

from .helpers import get

class Database:
    def execute(self, statement, returnResult=False):
        self.executeWithRetries(statement)

        if not returnResult:
            return
        
        try:
            rows = self.cursor.fetchall()

            result = []
        
            for row in rows:
                result.append(dict(row))

            return result
        except Exception as e:
            self.handleException(e)

    def get(self, table, columns, where, orderBy, orderType, limit=None):
        result = []

        wherePart = ''
        orderByPart = ''
        limitPart = ''

        if where:
            wherePart = f' where {where}'

        if orderBy:
            orderByPart = f' order by {orderBy} {orderType}'

        if limit:
            limitPart = f' limit {limit}'

        query = f'select {columns} from {table}{wherePart}{orderByPart}{limitPart};'

        self.executeWithRetries(query)

        try:
            rows = self.cursor.fetchall()

            for row in rows:
                result.append(dict(row))
        except Exception as e:
            self.handleException(e)

        return result

    def getFirst(self, table, columns, where, orderBy=None, orderType=None):
        result = {}

        rows = self.get(table, columns, where, orderBy, orderType, 1)

        if len(rows) > 0:
            result = rows[0]

        return result

    def executeWithRetries(self, query):
        maximumTries = 1000

        for i in range(0, maximumTries):
            try:
                self.cursor.execute(query)

                # if it's here it means it succeeded
                break
            except sqlite3.OperationalError as e:
                if str(e) == 'database is locked':
                    logging.error(f'Database locked. Retrying. {i + 1} of {maximumTries}.')

                    seconds = random.randrange(100, 1000) / 1000
                    time.sleep(seconds)
                else:
                    self.handleException(e)
                    break

        self.connection.commit()

    def insert(self, table, toInsert):
        if not toInsert:
            return

        items = []
        
        if isinstance(toInsert, list):
            items = toInsert
            toInsert = None

            logging.debug(f'Inserting into {len(items)} into {table}')
        else:
            logging.debug(f'Inserting into {table}: {toInsert}')
            items.append(toInsert)

        columns = []

        for key in items[0]:
            columns.append(key)

        columns = ', '.join(columns)

        groupsOfValues = []

        for item in items:            
            values = []
            
            for key, value in item.items():
                # escape single quotes
                if isinstance(value, str):
                    value = "'" + value.replace("'", "''") + "'"
                elif value == None:
                    value = 'null'

                values.append(str(value))

            values = ', '.join(values)
            values = f'({values})'

            groupsOfValues.append(values)

        groupsOfValues = ', '.join(groupsOfValues)

        query = ''

        if self.type == 'sqlite':
            query = f'insert or replace into {table} ({columns}) values {groupsOfValues};'
        elif self.type == 'mysql':
            query = f'replace into {table} ({columns}) values {groupsOfValues};'

        self.executeWithRetries(query)

    def makeTables(self, fileName):
        tables = helpers.getJsonFile(fileName)

        for tableName in tables:
            table = tables[tableName]

            columnList = []
            columns = get(table, 'columns')
            
            for column in columns:
                string = f'{column} {columns[column]}'
                columnList.append(string)

            columnsString = ', '.join(columnList)

            primaryKeys = get(table, 'primaryKeys')
            primaryKeysString = ', '.join(primaryKeys)

            if primaryKeysString:
                primaryKeysString = f', primary key({primaryKeysString})'

            statement = f'create table if not exists {tableName} ( {columnsString}{primaryKeysString} )'
            self.execute(statement)

    def open(self, name):
        if not name:
            return

        try:
            if self.type == 'sqlite':
                self.connection = sqlite3.connect(name)
                # to get column names
                self.connection.row_factory = sqlite3.Row
                self.cursor = self.connection.cursor()
            elif self.type == 'mysql':
                import mysql.connector                
                
                self.connection = mysql.connector.connect(host=get(name, 'host'), user=get(name, 'user'), passwd=get(name, 'password'))
                # buffered part is because otherwise get "Unread result found" error when you connection.commit without cursor.fetchAll
                self.cursor = self.connection.cursor(dictionary=True, buffered=True)

                self.cursor.execute(f'CREATE DATABASE IF NOT EXISTS {get(name, "database")} CHARACTER SET utf8 COLLATE utf8_general_ci;')
                self.cursor.execute(f'use {get(name, "database")};')

        except Exception as e:
            self.handleException(e)

    def handleException(self, e):
        helpers.handleException(e, 'Database error')

    def close(self):
        if self.connection:
            self.connection.commit()
            self.cursor.close()
            self.connection.close()

    def __init__(self, name=None, type='sqlite'):
        self.type = type
        self.connection = None
        self.cursor = None

        self.stringKeyType = 'text'

        if self.type == 'mysql':
            self.stringKeyType = 'varchar(100)'
        
        self.open(name)