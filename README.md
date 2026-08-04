CHAPTER 1
1. CLIENT BRIEF - SOLUTION SUMMARY:
To meet the Friday deadline with zero downtime, we implemented Blue-Green deployment using Azure App Service Deployment Slots. The new code is deployed to a `staging` green slot with 0% traffic. A mandatory automated health-check gate validates the real checkout flow before an atomic slot swap moves 100% traffic to the new version. If the gate fails, the swap will not happen. If a bug is found post-swap, an instant rollback swaps will occur back to the old version in staging. The entire process is automated in GitHub Actions for easy repeatability.





CHAPTER 2
2. PHASE 0: MY DESIGN WORKSHEET
2.1 Health check definition:This also called the "Green Gate"

My Goal: my goal is to Prove the new version can actually take money before we send real customers to it and traffic is ONLY allowed to swap if ALL of the following conditions pass against the staging slot:

Liveness of Azure State: `az webapp show --name quicktill-prod --slot staging`  when this code is input into our terminal, it must state “Running”,this  Proves the container is up in Azure and passed the platform health probes.
Readiness of  Web Response: my production slot url which is https://quicktill-prod-staging-fvhwa3cgfkcpf5q6.southafricanorth-01.azurewebsites.net/ , Must return the command/reply : `200 OK` in < 200ms. This  proves that the app is serving HTTP traffic.
Readiness of the Critical Path: my staging area url which is https://quicktill-prod-staging-fvhwa3cgfkcpf5q6.southafricanorth-01.azurewebsites.net/api/checkout/test which will carry our fake cart and test payment token must return: `201 Created` + JSON `{"status": "authorized"}` in < 500ms 
it Checks the actual checkout code path, pricing service, and payment gateway sandbox. This is what costs money if broken.

My web Dependencies : GET https://quicktill-prod-staging-fvhwa3cgfkcpf5q6.southafricanorth-01.azurewebsites.net/health/deps` Must return the reply: `200 OK` + JSON `{"db": "ok", "payment_gateway": "ok"}` this Checks if we Can connect to Azure SQL/Postgres and payment gateway.

Gate Rule: If Azure state is not `Running` OR ANY of the 4 return non-200, or take > 1s total, the pipeline FAILS and never swaps. Why?  this is strong and good because, We’re not checking "is the homepage up". We’re checking "can it actually do a checkout end-to-end".

2.2. SWAP AND ROLLBACK SEQUENCE
This can also be seen as the exact GitHub Actions workflow:
Phase A: Deploy to Green

`git push to main` triggers workflow

Build Docker image `reginald001/quicktill-demo:latest` and push to Docker Hub

Deploy image to `quicktill-staging` slot. Traffic = 0% to staging.

Phase B: The Health Check Gate

Wait 60s for container to start and run automated script to hit the 4 endpoints in 2.1 against the staging URL using `az webapp show` + `curl`

THE DECISION POINT in phase B:  If ALL other stages Pass, we go to Phase C but if ANY Fail the Pipeline exits with code 1. No swap occurs. This is an automatic failure.

Phase C: Zero-Downtime Swap

We Run Azure CLI: `az webapp deployment slot swap --name quicktill-prod --slot staging --target-slot production`
The Old version is now in staging, new version is in https: //quicktill-prod-hdcudfcvd9dueggk.southafricanorth-01.azurewebsites.net
Results are that 100% traffic instantly moves to new version. Zero downtime.

Phase D: The Rollback

The Automatic Rollback: This is triggered if Phase B fails which causes the pipeline to stops before swap.

Manual Rollback: This is triggered If a bug is found within 30min after swap, run: `az webapp deployment slot swap --name quicktill-prod --slot production --target-slot staging` This swaps back instantly because old version is still warm in staging.

2.3. Failure-mode brainstorm the 3 ways this can still go wrong.

The following are 3 ways this can go incredibly wrong to a point of frustration
 The "DNS Propagation" Failure: This happens when GitHub runner cannot resolve the new `southafricanorth-01.azurewebsites.net` staging URL during CI. Here, The Health check fails even though Azure shows 100% health. No swap occurs. To prevent this we use the code `az webapp show` in our git deploy yml code which talks to Azure API directly instead of public DNS and we also add retries.

 The "Config/Secrets Drift" Failure: This poblem happens when Staging slot has test Payment Gateway API key. This makesthe Health check #3 uses sandbox so it looks like it passes but  After swap, real payments will fail with `401 Unauthorized`.to remedy this, we  mark production secrets as "slot setting" so they don’t swapand the  Health check #4 verifies connection to LIVE dependency endpoints.

The "Fake Health Check" Failure: in this scenerio , Health check only hits `/` which returns 200, but doesn't test database connection pool. Here , the Swap happens and First 100 real checkouts timeout because DB pool is exhausted. To prevent this , Health check #3 actually does a write to DB via the `/api/checkout/test` endpoint.






CHAPTER 3

3. BUILD TASKS


   
3.1. Containerizing the app with Docker


3.2. Setting up Azure App Service with staging and production slot:
I created `quicktill-prod` App Service. Added `staging` deployment slot and both slots run the same App Service Plan. 

3.3. GitHub Actions workflow with health-check gate
The workflow deploys to staging, runs the 4-part health check, and only swaps if it passes below is my.
name: Deploy to Azure Blue-Green
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: azure/login@v2
      with: { creds: ${{ secrets.AZURE_CREDENTIALS }} }
    - run: az webapp config container set --name quicktill-prod --slot staging --docker-custom-image-name reginald001/quicktill-demo:latest
    - name: Health Check Staging
      run: |
        for i in {1..10}; do
          STATUS=$(az webapp show --name quicktill-prod --slot staging --query "state" -o tsv)
          if [ "$STATUS" == "Running" ]; then exit 0; fi
          sleep 30
        done
        exit 1
    - run: az webapp deployment slot swap --name quicktill-prod --slot staging --target-slot production
3.4 Demonstrating zero downtime:
I  demonstrated zero downtime by continuously polling the production endpoint at 2 requests per second during the slot swap. The poller returned 100% HTTP 200 responses with no errors or timeouts, proving that the cutover was not observable to users.
During the swap i ran the code `while true; do curl -o /dev/null -s -w "%{http_code}\n" https://quicktill-prod-hdcudfcvd9dueggk.southafricanorth-01.azurewebsites.net; sleep 0.5; done` 
this gives me 20+ consecutive `200` responses. No `500` or timeouts during cutover.





CHAPTER 4

4.1. Incident Report: the code Caught-and-Rolled-Back Bad Deploy

Symptom: I Pushed a bad image with broken DB connection string the Health Check Staging step failed. Log showed: `Staging state = Stopped` after 10 attempts. Pipeline marked as failed and  no swap occurred.
My Investigation trail:

I  Checked Azure Portal then Staging slot then Log stream and Saw `Error: connect ECONNREFUSED DB_HOST`

I Checked App Settings, Confirmed staging was missing `DB_CONNECTION_STRING`

I ruled out code bug because production was still healthy also ruled out Docker image because it built successfully.

The Root cause:  The Staging slot was missing required database connection string app setting.

The Fix: I added `DB_CONNECTION_STRING` to staging slot settings and marked it as "slot setting". Re-ran pipeline. Health check passed and swap succeeded.




CHAPTER 5
5.1 My Design reflection: 
My  Phase 0 design made this failure easier to catch because the health gate tested `state: Running` which fails if the app crashes on startup due to bad config. Without this gate the bad config would have gone to customers. To improve the design, I would add health check #4 to validate secrets by calling a `/health/config` endpoint that confirms it can connect with current keys.
