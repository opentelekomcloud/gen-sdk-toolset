:original_name: functiongraph_06_0202.html

.. _functiongraph_06_0202:

Example 1: Using a Timer Trigger to Periodically Download Files from an OBS Bucket
==================================================================================

Scenario
--------

This example guides you through the procedure for creating a Python 2.7 function and associating a timer trigger with it to periodically download files from an OBS bucket.

For details about how to call APIs, see :ref:`Calling APIs <functiongraph_06_0200>`.

Prerequisites
-------------

-  You have uploaded files to OBS and have recorded the file names, the bucket in which the files are stored, and the address of the bucket.
-  You have created an agency in IAM to allow FunctionGraph to access OBS and have recorded the name of the agency.

General Procedure
-----------------

Create a FunctionGraph function and associate a timer trigger with it to periodically download files from an OBS bucket. The procedure is as follows:

#. :ref:`Creating a Function <functiongraph_06_0108>`: Create a function for downloading files.
#. :ref:`Modifying the Metadata of a Function <functiongraph_06_0111>`: Modify the OBS address, OBS bucket name, and file name in the function configuration.
#. :ref:`Executing a Function Synchronously <functiongraph_06_0125>`: Verify whether the function can successfully download files from the OBS bucket.
#. :ref:`Creating a Trigger <functiongraph_06_0122>`: Create a timer trigger to periodically download files.

.. _functiongraph_06_0202__section14318132594418:

Step 1: Create a Function for Downloading Files from OBS
--------------------------------------------------------

URI: **POST /v2/**\ *{project_id}*\ **/fgs/functions**

For details, see :ref:`Creating a Function <functiongraph_06_0108>`.

-  Sample request

   .. code-block:: text

      POST  https://{Endpoint}/v2/{project_id}/fgs/functions
      {
       "code_filename": "index.zip",
       "code_type": "inline",
       "func_code": {
        "file": "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"
       },
       "func_name": "download_file_from_obs",
       "handler": "index.handler",
       "memory_size": 256,
       "package": "default",
       "runtime": "Python2.7",
       "timeout": 30
      }

-  Sample response

   .. code-block::

      {
       "func_urn": "urn:fss:{project_name}:{project_id}:function:default:download_file_from_obs:latest",
       "func_name": "download_file_from_obs",
       "domain_id": "89fexxxd636",
       "namespace": "{project_id}",
       "project_name": "xxx",
       "package": "default",
       "runtime": "Python2.7",
       "timeout": 30,
       "handler": "index.handler",
       "memory_size": 256,
       "cpu": 400,
       "code_type": "inline",
       "code_filename": "index.zip",
       "code_size": 1707,
       "digest": "68891a6778848a78bd37a8c0798c91d75a5c87aee6e901303047a52edf05bf2170aac4149d79b3f6a40efe78406a83bf6d8683e7b25da4f0c07e7493aa4ccdcd",
       "version": "latest",
       "image_name": "latest-200603162219@zr2ym",
       "last_modified": "2020-06-03T16:22:19+08:00",
       "strategy_config": {
        "concurrency": -1
       },
       "StrategyConfig": {},
       "enterprise_project_id": "0"
      }

   Record the URN of the function, that is, the value of **func_urn** in the response.

Step 2: Modify the OBS Address, Bucket Name, and File Name in the Function Configurations
-----------------------------------------------------------------------------------------

URI: **PUT /v2/**\ *{project_id}*\ **/fgs/functions/**\ *{function_urn}*\ **/config**

For details, see :ref:`Modifying the Metadata of a Function <functiongraph_06_0111>`.

-  Sample request

   .. code-block:: text

      PUT  https://{Endpoint}/v2/{project_id}/fgs/functions/{function_urn}/config
      {
       "func_name": "download_file_from_obs",
       "handler": "index.handler",
       "memory_size": 256,
       "runtime": "Python2.7",
       "timeout": 30,
       "user_data": "{\"obs_address\":\"obs.xxx.xxx.com\",\"srcBucket\":\" xxx\",\"srcObjName\":\"xxx\"}",
       "xrole": "xxx"
      }

   **function_urn** indicates the function URN recorded in :ref:`Step 1: Create a Function for Downloading Files from OBS <functiongraph_06_0202__section14318132594418>`; **obs_address** indicates the OBS address; **srcBucket** indicates the name of an OBS bucket, **srcObjName** indicates a file name, and **xrole** indicates an agency name.

-  Sample response

   .. code-block::

      {
       "func_urn": "urn:fss:{project_name}:{project_id}:function:default:download_file_from_obs:latest",
       "func_name": "download_file_from_obs",
       "domain_id": "89fexxxd636",
       "namespace": "{project_id}",
       "project_name": "xxx",
       "package": "default",
       "runtime": "Python2.7",
       "timeout": 30,
       "handler": "index.handler",
       "memory_size": 256,
       "cpu": 400,
       "code_type": "inline",
       "code_filename": "index.zip",
       "code_size": 1707,
       "user_data": "{\"obs_address\":\"obs.xxx.xxx.com\",\"srcBucket\":\"xxx\",\"srcObjName\":\"xxx\"}",
       "digest": "68891a6778848a78bd37a8c0798c91d75a5c87aee6e901303047a52edf05bf2170aac4149d79b3f6a40efe78406a83bf6d8683e7b25da4f0c07e7493aa4ccdcd",
       "version": "latest",
       "image_name": "latest-200603165355@varrp",
       "xrole": "xxx",
       "app_xrole": "xxx",
       "last_modified": "2020-06-03T17:25:03+08:00",
       "strategy_config": {
        "concurrency": -1
       },
       "StrategyConfig": {},
       "enterprise_project_id": "0"
      }

Step 3: Test the Function
-------------------------

URI: **POST /v2/**\ *{project_id}*\ **/fgs/functions/**\ *{function_urn}*\ **/invocations**

For details, see :ref:`Executing a Function Synchronously <functiongraph_06_0125>`.

-  Sample request

   .. code-block:: text

      POST  https://{Endpoint}/v2/{project_id}/fgs/functions/{function_urn}/invocations
      {
       "message": "download file"
      }

   **function_urn** indicates the function URN recorded in :ref:`Step 1: Create a Function for Downloading Files from OBS <functiongraph_06_0202__section14318132594418>`.

-  Sample response

   .. code-block::

      "The object downloaded successfully from OBS, and the size is 14 KB"

Step 4: Create a Timer Trigger to Periodically Download Files from OBS
----------------------------------------------------------------------

URI: **POST /v2/**\ *{project_id}*\ **/fgs/triggers/**\ *{function_urn}*

For details, see :ref:`Creating a Trigger <functiongraph_06_0122>`.

-  Sample request

   .. code-block:: text

      POST  https://{Endpoint}/v2/{project_id}/fgs/triggers/{function_urn}
      {
       "event_data": {
        "name": "Timer-download",
        "schedule_type": "Rate",
        "schedule": "1d"
       },
       "event_type_code": "MessageCreated",
       "trigger_status": "ACTIVE",
       "trigger_type_code": "TIMER"
      }

   **function_urn** indicates the function URN recorded in :ref:`Step 1: Create a Function for Downloading Files from OBS <functiongraph_06_0202__section14318132594418>`.

   The preceding example request is used to download files from the specified OBS bucket every day.

-  Sample response

   .. code-block::

      {
       "trigger_id": "461bbe95-c85b-4dc9-a306-9701e77f1d66",
       "trigger_type_code": "TIMER",
       "trigger_status": "ACTIVE",
       "event_data": {
        "name": "Timer-download",
        "schedule": "1d",
        "schedule_type": "Rate"
       },
       "last_updated_time": "2020-06-04T10:33:30+08:00",
       "created_time": "2020-06-04T10:33:30+08:00"
      }
