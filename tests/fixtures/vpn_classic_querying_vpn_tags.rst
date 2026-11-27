:original_name: vpn_api_1019.html

.. _vpn_api_1019:

Querying VPN Tags
=================

Function
--------

This API is used to query tags of a specified VPN.

URI
---

GET /v2.0/{project_id}/ipsec-site-connections/{resource_id}/tags

.. note::

   In the URI, **project_id** indicates the project ID, and **resource_id** indicates the ID of the target resource.

Request
-------

None

Response
--------

:ref:`Table 1 <en-us_topic_0000001807530352__en-us_topic_0000001591736537_en-us_topic_0103470567_table1135702419184>` describes the response parameter.

.. _en-us_topic_0000001807530352__en-us_topic_0000001591736537_en-us_topic_0103470567_table1135702419184:

.. table:: **Table 1** Response parameter

   ========= ================== ===========================
   Parameter Type               Description
   ========= ================== ===========================
   tags      List<resource_tag> Specifies the list of tags.
   ========= ================== ===========================

.. table:: **Table 2** Description of field **resource_tag**

   +-----------------------+-----------------------+----------------------------------------------------+
   | Name                  | Type                  | Description                                        |
   +=======================+=======================+====================================================+
   | key                   | String                | Specifies the tag key.                             |
   |                       |                       |                                                    |
   |                       |                       | The key                                            |
   |                       |                       |                                                    |
   |                       |                       | -  Must be unique for a resource.                  |
   |                       |                       | -  Cannot be left blank.                           |
   |                       |                       | -  Can contain a maximum of 36 characters.         |
   |                       |                       | -  Can contain only the following character types: |
   |                       |                       |                                                    |
   |                       |                       |    -  Uppercase letters                            |
   |                       |                       |    -  Lowercase letters                            |
   |                       |                       |    -  Digits                                       |
   |                       |                       |    -  Hyphens (-) and underscores (_)              |
   +-----------------------+-----------------------+----------------------------------------------------+
   | value                 | String                | Specifies the tag value.                           |
   |                       |                       |                                                    |
   |                       |                       | The value                                          |
   |                       |                       |                                                    |
   |                       |                       | -  Can contain a maximum of 43 characters.         |
   |                       |                       | -  Can contain only the following character types: |
   |                       |                       |                                                    |
   |                       |                       |    -  Uppercase letters                            |
   |                       |                       |    -  Lowercase letters                            |
   |                       |                       |    -  Digits                                       |
   |                       |                       |    -  Hyphens (-) and underscores (_)              |
   +-----------------------+-----------------------+----------------------------------------------------+

Example
-------

-  Example request

   .. code-block:: text

      GET /v2.0/{project_id}/ipsec-site-connections/{resource_id}/tags

-  Example response

   .. code-block::

      {
             "tags": [
              {
                  "key": "key1",
                  "value": "value1"
              },
              {
                  "key": "key2",
                  "value": "value3"
              }
          ]
      }

Returned Values
---------------

For details, see :ref:`Common Returned Values <en-us_topic_0000001854089293>`.
