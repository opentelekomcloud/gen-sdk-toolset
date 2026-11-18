:original_name: functiongraph_06_0204.html

.. _functiongraph_06_0204:

Example 2: Creating a Function by Uploading Code to an OBS Bucket
=================================================================

Scenario
--------

This example guides you through the procedure for uploading local code to an OBS bucket and creating a Python 2.7 function using the link URL of the OBS bucket.

For details about how to call APIs, see :ref:`Calling APIs <functiongraph_06_0200>`.

Prerequisites
-------------

An OBS bucket has been created.

General Procedure
-----------------

After writing function code in your local environment, upload the code file to an OBS bucket and use the link URL of the OBS bucket to create a function. The procedure is as follows:

#. Write code in your local environment to create a function project.
#. Compress the code file into a ZIP package, upload the package to the OBS bucket, and record the link URL of this bucket.
#. Call the API in :ref:`Creating a Function <functiongraph_06_0108>` to create a function using the link URL of the OBS bucket.

Step 1: Create a Function Project
---------------------------------

#. Write code for printing text **helloworld**.

   Open a text editor, compile a HelloWorld function, and save the code file as **helloworld.py**. The code is as follows:

   .. code-block::

      def printhello():
          print 'Hello world!'

#. Define a FunctionGraph function.

   Open a text editor, define a function, and save the function file as **index.py** under the same directory as the **helloworld.py** file. The function code is as follows:

   .. code-block::

      import json
      import helloworld

      def handler (event, context):
          output =json.dumps(event)
          helloworld.printhello()
          return output

Step 2: Upload the Project to an OBS Bucket
-------------------------------------------

#. In the function project, select the **helloworld.py** and **index.py** files and compress them into **fss_examples_python2.7.zip**.

#. .. _functiongraph_06_0204__li1966633145116:

   Upload the **fss_examples_python2.7.zip** package to the OBS bucket and record the link URL of the OBS bucket.

Step 3: Call the Function Creation API to Create a Function Using the Link URL of the OBS Bucket
------------------------------------------------------------------------------------------------

URI: **POST /v2/**\ *{project_id}*\ **/fgs/functions**

For details about the API, see :ref:`Creating a Function <functiongraph_06_0108>`.

-  Sample request

   .. code-block:: text

      POST  https://{Endpoint}/v2/{project_id}/fgs/functions
      {
       "code_type": "obs",
       "code_url": "https://test.obs.xxx.xxx.com/fss_examples_python2.7.zip",
       "func_name": "create_function_from_obs",
       "handler": "index.handler",
       "memory_size": 256,
       "package": "default",
       "runtime": "Python2.7",
       "timeout": 30
      }

   **code_url** indicates the link URL of the OBS bucket recorded in :ref:`2 <functiongraph_06_0204__li1966633145116>`.

-  Sample response

   .. code-block::

      {
       "func_urn": "urn:fss:{project_name}:{project_id}:function:default:create_function_from_obs:latest",
       "func_name": "create_function_from_obs",
       "domain_id": "0503xxxa960",
       "namespace": "{project_id}",
       "project_name": "xxx",
       "package": "default",
       "runtime": "Python2.7",
       "timeout": 30,
       "handler": "index.handler",
       "memory_size": 256,
       "cpu": 400,
       "code_type": "obs",
       "code_url": "https://test.obs.xxx.xxx.com/fss_examples_python2.7.zip",
       "code_filename": "fss_examples_python2.7.zip",
       "code_size": 436,
       "digest": "3af770ada27514564b1a20d964cba4b35f432fa40f9fc4f4f7c1f0d2f42eac6cb4db1358c195235966b05f66b4664e7bf31c3f384a9066b3d1fcc3e96b4c3f65",
       "version": "latest",
       "image_name": "latest-200619100734@gjf4p",
       "last_modified": "2020-06-19T10:07:34+08:00",
       "strategy_config": {
        "concurrency": -1
       },
       "StrategyConfig": {},
       "enterprise_project_id": "0"
      }
