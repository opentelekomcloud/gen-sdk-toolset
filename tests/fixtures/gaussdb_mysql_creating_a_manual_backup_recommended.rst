:original_name: gaussdb_06_0003.html

.. _gaussdb_06_0003:

Creating a Manual Backup
========================

Function
--------

This API is used to create a manual backup. Before using this API:

-  Learn how to :ref:`authorize and authenticate <gaussdb_03_0001>` it.
-  Obtain the required :ref:`region and endpoint <gaussdb_00_0003>`.

URI
---

POST /v3/{project_id}/backups/create

.. table:: **Table 1** URI parameters

   +-----------------+-----------------+-----------------+----------------------------------------------------------------------------+
   | Parameter       | Mandatory       | Type            | Description                                                                |
   +=================+=================+=================+============================================================================+
   | project_id      | Yes             | String          | Project ID of a tenant in a region.                                        |
   |                 |                 |                 |                                                                            |
   |                 |                 |                 | To obtain this value, see :ref:`Obtaining a Project ID <gaussdb_10_0004>`. |
   +-----------------+-----------------+-----------------+----------------------------------------------------------------------------+

Request Parameters
------------------

.. table:: **Table 2** Request header parameters

   ============ ========= ====== ===========
   Parameter    Mandatory Type   Description
   ============ ========= ====== ===========
   X-Auth-Token Yes       String User token.
   X-Language   No        String Language.
   ============ ========= ====== ===========

.. table:: **Table 3** Request body parameters

   +-------------+-----------+--------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter   | Mandatory | Type   | Description                                                                                                                                                                       |
   +=============+===========+========+===================================================================================================================================================================================+
   | instance_id | Yes       | String | DB instance ID, which is compliant with the UUID format.                                                                                                                          |
   +-------------+-----------+--------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | name        | Yes       | String | Backup name. The value must be 4 to 64 characters in length and start with a letter. It is case-sensitive and can contain only letters, digits, hyphens (-), and underscores (_). |
   +-------------+-----------+--------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | description | No        | String | Backup description. It contains a maximum of 256 characters and cannot contain the special characters ``(>!<"&'=)``                                                               |
   +-------------+-----------+--------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Response Parameters
-------------------

**Status code: 201**

.. table:: **Table 4** Response body parameters

   +-----------+---------------------------------------------------------+---------------------+
   | Parameter | Type                                                    | Description         |
   +===========+=========================================================+=====================+
   | backup    | :ref:`backup <gaussdb_06_0003__response_backup>` object | Backup information. |
   +-----------+---------------------------------------------------------+---------------------+
   | job_id    | String                                                  | Task ID.            |
   +-----------+---------------------------------------------------------+---------------------+

.. _gaussdb_06_0003__response_backup:

.. table:: **Table 5** backup

   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter             | Type                  | Description                                                                                                                                           |
   +=======================+=======================+=======================================================================================================================================================+
   | id                    | String                | Backup ID.                                                                                                                                            |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
   | name                  | String                | Backup name.                                                                                                                                          |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
   | description           | String                | Backup description.                                                                                                                                   |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
   | begin_time            | String                | Backup start time in the "yyyy-mm-ddThh:mm:ssZ" format, where "T" indicates the start time of the time field, and "Z" indicates the time zone offset. |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
   | status                | String                | Backup status. Value:                                                                                                                                 |
   |                       |                       |                                                                                                                                                       |
   |                       |                       | -  **BUILDING**: Backup in progress                                                                                                                   |
   |                       |                       | -  **COMPLETED**: Backup completed                                                                                                                    |
   |                       |                       | -  **FAILED**: Backup failed                                                                                                                          |
   |                       |                       | -  **AVAILABLE**: Backup available                                                                                                                    |
   |                       |                       |                                                                                                                                                       |
   |                       |                       | Valid value:                                                                                                                                          |
   |                       |                       |                                                                                                                                                       |
   |                       |                       | -  BUILDING                                                                                                                                           |
   |                       |                       | -  COMPLETED                                                                                                                                          |
   |                       |                       | -  FAILED                                                                                                                                             |
   |                       |                       | -  AVAILABLE                                                                                                                                          |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
   | type                  | String                | Backup type. Value:                                                                                                                                   |
   |                       |                       |                                                                                                                                                       |
   |                       |                       | **manual**: manual full backup                                                                                                                        |
   |                       |                       |                                                                                                                                                       |
   |                       |                       | Valid value:                                                                                                                                          |
   |                       |                       |                                                                                                                                                       |
   |                       |                       | manual                                                                                                                                                |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
   | instance_id           | String                | DB instance ID.                                                                                                                                       |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+

**Status code: 400**

.. table:: **Table 6** Response body parameters

   ========== ====== ==============
   Parameter  Type   Description
   ========== ====== ==============
   error_code String Error code.
   error_msg  String Error message.
   ========== ====== ==============

**Status code: 500**

.. table:: **Table 7** Response body parameters

   ========== ====== ==============
   Parameter  Type   Description
   ========== ====== ==============
   error_code String Error code.
   error_msg  String Error message.
   ========== ====== ==============

Example Request
---------------

Creating a Manual Backup

.. code-block::

   POST https://gaussdb-mysql.eu-de.otc.t-systems.com/v3/619d3e78f61b4be68bc5aa0b59edcf7b/backups/create
   {
     "instance_id" : "07033b125fd94a8a96896f8bcfee6ddain07",
     "name" : "backup-1",
     "description": "Manual backup"
   }

Example Response
----------------

**Status code: 201**

Success.

.. code-block::

   {
     "backup" : {
       "id" : "2f4ddb93-b901-4b08-93d8-1d2e472f30fe",
       "name" : "backup-1",
       "description": "Manual backup"
       "begin_time" : "2020-07-07T01:17:05+0800",
       "status" : "BUILDING",
       "type" : "manual",
       "instance_id" : "07033b125fd94a8a96896f8bcfee6ddain07"
     },
     "job_id" : "e0fbbfc8-1ac4-4721-b9e9-7dd685c5bdd7"
   }

Status Code
-----------

For details, see :ref:`Status Codes <gaussdb_10_0002>`.

Error Code
----------

For details, see :ref:`Error Codes <gaussdb_10_0003>`.
