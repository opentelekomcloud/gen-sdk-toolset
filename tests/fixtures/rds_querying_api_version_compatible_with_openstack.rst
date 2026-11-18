:original_name: en-us_topic_0057306832.html

.. _en-us_topic_0057306832:

Querying a Specified API Version Information (Compatible with OpenStack)
========================================================================

Function
--------

This API is used to query the specified API version.

-  Before calling an API, you need to understand the API in :ref:`Authentication <rds_03_0001>`.
-  Before calling this API, obtain the required `region and endpoint <https://docs.otc.t-systems.com/en-us/endpoint/index.html>`__.

URI
---

-  URI format

   PATH: /v1.0

   Method: GET

Request
-------

None

Response
--------

-  Normal response

   .. table:: **Table 1** Parameter description

      +-----------------------+-----------------------+----------------------------------------------------------------------------------------------+
      | Name                  | Type                  | Description                                                                                  |
      +=======================+=======================+==============================================================================================+
      | versions              | Object                | Indicates the list of detailed API version information.                                      |
      |                       |                       |                                                                                              |
      |                       |                       | For details, see :ref:`Table 2 <en-us_topic_0057306832__t5963fff962ed43abb7a3e7d46742f177>`. |
      +-----------------------+-----------------------+----------------------------------------------------------------------------------------------+
      | version               | Object                | Indicates the list of detailed API version information.                                      |
      |                       |                       |                                                                                              |
      |                       |                       | For details, see :ref:`Table 2 <en-us_topic_0057306832__t5963fff962ed43abb7a3e7d46742f177>`. |
      +-----------------------+-----------------------+----------------------------------------------------------------------------------------------+

   .. _en-us_topic_0057306832__t5963fff962ed43abb7a3e7d46742f177:

   .. table:: **Table 2** versions field data structure description

      +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
      | Name                  | Type                  | Description                                                                                           |
      +=======================+=======================+=======================================================================================================+
      | id                    | String                | Indicates the API version.                                                                            |
      +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
      | links                 | Array                 | Indicates the API link information.                                                                   |
      |                       |                       |                                                                                                       |
      |                       |                       | For details, see :ref:`Table 3 <en-us_topic_0057306832__t39ce8ee145d0420f9b392b8b6897bd15>`.          |
      +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
      | status                | String                | Indicates the version status.                                                                         |
      +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
      | updated               | String                | Indicates the version update time.                                                                    |
      |                       |                       |                                                                                                       |
      |                       |                       | The format is yyyy-mm-dd Thh:mm:ssZ.                                                                  |
      |                       |                       |                                                                                                       |
      |                       |                       | **T** is the separator between the calendar and the hourly notation of time. **Z** indicates the UTC. |
      +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------+

   .. _en-us_topic_0057306832__t39ce8ee145d0420f9b392b8b6897bd15:

   .. table:: **Table 3** links field data structure description

      +------+--------+------------------------------------------------------------------+
      | Name | Type   | Description                                                      |
      +======+========+==================================================================+
      | href | String | Indicates the API URL and the value is **""**.                   |
      +------+--------+------------------------------------------------------------------+
      | rel  | String | Its value is **self**, indicating that **href** is a local link. |
      +------+--------+------------------------------------------------------------------+

-  Example normal response

   .. code-block:: text

      {
          "version": {
              "id": "v1.0",
              "links": [{
                  "href": "",
                  "rel": "self"
              }],
              "status": "CURRENT",
              "updated": "2017-03-23T17:34:02Z"
          },
          "versions": {
              "id": "v1.0",
              "links": [{
                  "href": "",
                  "rel": "self"
              }],
              "status": "CURRENT",
              "updated": "2017-03-23T17:34:02Z"
          }
      }

-  Abnormal response

   For details, see :ref:`Abnormal Request Results <en-us_topic_0032488197>`.

Status Code
-----------

-  Normal

   200

-  Abnormal

   For details, see :ref:`Status Codes <en-us_topic_0032488240>`.

Error Code
----------

For details, see :ref:`Error Codes <en-us_topic_0032488241>`.
