# Stable Protocol Indexer

## Introduction

To speed up the app we need an indexer of the blockchain of our contracts. 
This service is required to display operations in the dapp.  
The indexer query the status of the contracts
and write to mongo database, so the app query the mongo instead of blockchain (slow).

### Requirements

* Mongo db
* Python installed

### Usage

**Requirement and installation**
 
* We need Python 3.6+

Install libraries

`pip install -r requirements.txt`

**Usage**

Select settings from settings/ and copy to ./config.json also change url, db uri and db name. 

**Run**

`python ./app_run_indexer.py `


