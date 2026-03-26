# **Open-Coding Protocol for Inefficiency Pattern Analysis (RQ2)**

This document describes the detailed open-coding protocol used to identify and categorize inefficiency patterns in LLM-generated SQL queries.

------

## **1. Coding Objective**

The goal of this analysis is to systematically identify recurring inefficiency patterns in LLM-generated SQL queries that are semantically correct but suboptimal in execution efficiency. Each inefficiency pattern corresponds to a structural or logical issue that leads to unnecessary computational cost, such as redundant scans, delayed filtering, or suboptimal join strategies.

------

## **2. Coding Unit**

The basic unit of analysis is a query pair:

- LLM-generated SQL (inefficient)
- Expert-optimized SQL (efficient reference)
- Corresponding execution plans

Annotators analyze both:

- query structure differences, and
- execution plan discrepancies.

------

## **3. Open-Coding Procedure**

We follow a **three-stage open-coding process**, adapted from standard qualitative analysis methodology:

------

### **3.1 Initial Open Coding (Exploratory Phase)**

In the first stage, we conduct an exploratory analysis on a **randomly sampled subset (10%)** of the full benchmark.

For each selected task:

- We collect:
  - LLM-generated SQL queries,
  - corresponding expert-optimized SQL,
  - execution plans (via `EXPLAIN ANALYZE`).
- Three experts independently:
  - compare generated queries against optimized counterparts,
  - analyze execution plan differences (e.g., scanned rows, operator ordering),
  - identify potential sources of inefficiency.
- Annotators assign free-form labels describing inefficiency causes, such as:
  - “late filtering after aggregation”
  - “redundant nested subquery”
  - “missing index pruning”
  - “inefficient join order”

At this stage:

- No predefined taxonomy is imposed;
- Multiple labels per query are allowed;
- The goal is to **maximize coverage of possible inefficiency phenomena.**

------

### **3.2 Preliminary Taxonomy Construction (Axial Coding Phase)**

Based on the initial coding results:

- All collected labels are aggregated and normalized through:
  - merging semantically equivalent labels,
  - splitting overly coarse labels,
  - removing ambiguous or non-actionable descriptions.
- Three experts independently re-label the sampled queries using the normalized label set.
- Annotation consistency is measured using **Cohen’s Kappa**:
  - We obtain κ = **0.91**, indicating strong agreement.
- Disagreements are resolved through discussion, guided by:
  - query structure,
  - execution plan evidence,
  - optimization principles.
- Similar labels are grouped into higher-level concepts, forming a **preliminary taxonomy** of inefficiency patterns.

------

### **3.3 Full Taxonomy Construction (Selective Coding Phase)**

Using the preliminary taxonomy:

- The remaining 90% of query instances are annotated independently by three experts.
- During this process:
  - Existing labels are reused whenever applicable;
  - New labels are introduced only when:
    - they cannot be expressed by existing categories,
    - and they appear in multiple independent cases.
- The taxonomy is iteratively refined through:
  - expert discussion,
  - merging or restructuring categories,
  - re-evaluating borderline cases.
- Final disagreements are resolved by adjudication.

------

## **4. Independence and Adjudication**

- All initial coding is conducted **independently** by three experts.
- Annotators:
  - do not share intermediate labels,
  - do not access others’ annotations.
- Disagreements are resolved through:
  - discussion based on query plans and SQL structure,
  - final decision by consensus or adjudicator.

------

## **5. Reliability and Bias Mitigation**

To ensure robustness of qualitative findings:

- Multiple independent coders
  - Reduces individual bias in pattern identification.
- Iterative refinement
  - Labels are refined across multiple rounds.
- Consensus-based consolidation
  - Final categories are agreed upon by all experts.
- Anchoring to execution evidence
  - All patterns must correspond to measurable inefficiency (e.g., increased scanned rows).

