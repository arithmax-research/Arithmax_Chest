# PyKX & q/kdb+ Quick Reference Cheat Sheet

## 1. Setting Up PyKX
PyKX integrates the high-performance q/kdb+ time-series database with Python.

```python
import pykx as kx

# Start an embedded q session (requires license for full features)
# Or connects to a local/licensed instance automatically
```

### IPC Connections (Connecting to a running q process)
```python
# Connect to a q process running on localhost port 5000
q = kx.SyncQConnection(host='localhost', port=5000)

# Execute q code over IPC
result = q('1 + 1')
```

---

## 2. Data Types & Conversion
PyKX objects cleanly convert between q, Python, NumPy, and Pandas.

```python
# Create a PyKX object from Python
kx_list = kx.toq([1, 2, 3])
kx_sym = kx.toq('my_symbol')

# Convert PyKX object back to Python/Pandas
py_list = kx_list.py()
df = kx.toq({'a': [1, 2], 'b': [3, 4]}).pd()  # Convert q table to Pandas DataFrame
np_arr = kx_list.np()                         # Convert q list to NumPy array
```

---

## 3. Core q Operations (Embedded or IPC)
You can evaluate raw q expressions using `kx.q('expression')` or `q('expression')`.

### Basic Syntax & Math
* **Right-to-Left Evaluation:** `1 + 2 * 3` evaluates to `9` in q (not `7`). Use parentheses: `1 + (2 * 3)`.
* **Atomic Functions:** `1 2 3 + 10` $\rightarrow$ `11 12 13`

### Most Important Operators & Idioms
| Operator | q Syntax | Description | Example |
| :--- | :--- | :--- | :--- |
| **Join** | `,` | Joins atoms, lists, or tables | `1 2 , 3 4` $\rightarrow$ `1 2 3 4` |
| **Drop** | `_` | Drops $N$ items from a list or drops columns | `2 _ 10 20 30` $\rightarrow$ `,30` |
| **Take** | `#` | Takes $N$ items from a list or reshapes | `2 # 10 20 30` $\rightarrow$ `10 20` |
| **Find** | `?` | Returns index of first occurrence | `10 20 30 ? 20` $\rightarrow$ `1` |
| **Apply/Index** | `.` or `@` | Index at depth (`.`) or index at top level (`@`) | `.[(1 2; 3 4); 0 1]` $\rightarrow$ `2` |
| **Each** | `'` | Applies a function to each element | `({x*2}' 1 2 3)` $\rightarrow` `2 4 6` |

---

## 4. Tables and q-SQL
q features a built-in query language called q-SQL.

### Creating Tables
```python
# Create a table directly in q
kx.q('trade: ([] sym: `AAPL`GOOG`AAPL; price: 150.5 2800.2 151.0; size: 100 50 200)')

# Create from PyKX by converting a dictionary
t = kx.toq({'sym': ['AAPL', 'MSFT'], 'price': [150.0, 250.0]})
```

### Table Operations (q-SQL)
* **Select:** `kx.q("select from trade where sym=`AAPL")`
* **Aggregation:** `kx.q("select avg price by sym from trade")`
* **Update / Add Column:** `kx.q("update total: price * size from trade")`

---

## 5. Key System Commands
Run these inside a string with `kx.q('\\cmd')` or within the q terminal.

* `\p [int]` — View or set the port.
* `\a` — List all tables in the current namespace.
* `\v` — List all variables in the current namespace.
* `\t [expr]` — Time the execution of an expression.
* `\\` — Quit the q session.
