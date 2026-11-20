:original_name: aom_04_0014.html

.. _aom_04_0014:

Querying Details About a Specified Alarm Action Rule
====================================================

Scenario
--------

This section describes how to query an alarm action rule by name.

Obtaining Basic Information
---------------------------

Before querying the details about an alarm action rule, obtain its rule name first. You can call the API for obtaining the alarm action rule list or go to the AOM 2.0 console to obtain the rule name.


Querying Details About a Specified Alarm Action Rule
----------------------------------------------------

-  URI format

   URI format: GET /v2/{*project_id*}/alert/action-rules/{*rule_name*}

-  Example request

   GET https://{Endpoint}/v2/{project_id}/alert/action-rules/{rule_name}

   You can obtain the value of *{aom_endpoint}* from `Regions and Endpoints <https://docs.otc.t-systems.com/en-us/endpoint/index.html>`__.

-  Example response

   .. code-block::

      {
          "create_time": 1665991889597,
          "notification_template": "aom.built-in.template.zh",
          "project_id": "2xxxxxxxxxxxxxxxxxxxxxxf",
          "rule_name": "1112222",
          "smn_topics": [{
              "display_name": "",
              "name": "gxxxxxt",
              "push_policy": 0,
              "status": 0,
              "topic_urn": "urn:smn:xxxx:2xxxxxxxxxxxxxxxxxxxxxxf:gxxxxxt"
          }],
          "time_zone": "xx/XXX",
          "type": "1",
          "update_time": 1665991889597,
          "user_name": "kxxxxxxxt"
      }
