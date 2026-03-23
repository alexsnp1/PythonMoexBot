package db;

import model.SpreadRule;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

public class DatabaseService {
    private final String dbUrl;

    public DatabaseService(Path dbPath) {
        this.dbUrl = "jdbc:sqlite:" + dbPath.toAbsolutePath();
    }

    public void init() {
        // Ensure parent exists when using custom paths.
        // For simple relative paths, dbPath.toAbsolutePath() already has a parent.
        try {
            try (Connection c = DriverManager.getConnection(dbUrl);
                 Statement st = c.createStatement()) {
                st.execute("""
                        CREATE TABLE IF NOT EXISTS rules (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            formula TEXT NOT NULL,
                            upper_bound REAL,
                            lower_bound REAL,
                            last_alert_time INTEGER
                        );
                        """);
                st.execute("CREATE INDEX IF NOT EXISTS idx_rules_user_id ON rules(user_id);");
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to initialize SQLite database", e);
        }
    }

    public long addRule(long userId, String formula, Double upperBound, Double lowerBound) {
        String sql = "INSERT INTO rules(user_id, formula, upper_bound, lower_bound, last_alert_time) VALUES(?,?,?,?,NULL)";
        try (Connection c = DriverManager.getConnection(dbUrl);
             PreparedStatement ps = c.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
            ps.setLong(1, userId);
            ps.setString(2, formula);
            if (upperBound == null) ps.setNull(3, java.sql.Types.REAL);
            else ps.setDouble(3, upperBound);
            if (lowerBound == null) ps.setNull(4, java.sql.Types.REAL);
            else ps.setDouble(4, lowerBound);

            ps.executeUpdate();

            try (ResultSet keys = ps.getGeneratedKeys()) {
                if (keys.next()) return keys.getLong(1);
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to add rule", e);
        }
        throw new IllegalStateException("Failed to add rule: no generated key");
    }

    public List<SpreadRule> listRules(long userId) {
        String sql = """
                SELECT id, user_id, formula, upper_bound, lower_bound, COALESCE(last_alert_time, 0) as last_alert_time
                FROM rules
                WHERE user_id = ?
                ORDER BY id
                """;
        List<SpreadRule> out = new ArrayList<>();
        try (Connection c = DriverManager.getConnection(dbUrl);
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, userId);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    out.add(fromRow(rs));
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to list rules", e);
        }
        return out;
    }

    public List<SpreadRule> getAllRules() {
        String sql = """
                SELECT id, user_id, formula, upper_bound, lower_bound, COALESCE(last_alert_time, 0) as last_alert_time
                FROM rules
                ORDER BY user_id, id
                """;
        List<SpreadRule> out = new ArrayList<>();
        try (Connection c = DriverManager.getConnection(dbUrl);
             PreparedStatement ps = c.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                out.add(fromRow(rs));
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to fetch all rules", e);
        }
        return out;
    }

    public boolean removeRule(long userId, long ruleId) {
        String sql = "DELETE FROM rules WHERE user_id = ? AND id = ?";
        try (Connection c = DriverManager.getConnection(dbUrl);
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, userId);
            ps.setLong(2, ruleId);
            int updated = ps.executeUpdate();
            return updated > 0;
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to remove rule", e);
        }
    }

    public boolean updateThresholds(long userId, long ruleId, Double upperBound, Double lowerBound) {
        String sql = """
                UPDATE rules
                SET upper_bound = ?, lower_bound = ?
                WHERE user_id = ? AND id = ?
                """;
        try (Connection c = DriverManager.getConnection(dbUrl);
             PreparedStatement ps = c.prepareStatement(sql)) {
            if (upperBound == null) ps.setNull(1, java.sql.Types.REAL);
            else ps.setDouble(1, upperBound);
            if (lowerBound == null) ps.setNull(2, java.sql.Types.REAL);
            else ps.setDouble(2, lowerBound);
            ps.setLong(3, userId);
            ps.setLong(4, ruleId);
            int updated = ps.executeUpdate();
            return updated > 0;
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to update thresholds", e);
        }
    }

    public boolean updateLastAlertTime(long userId, long ruleId, long nowMillis) {
        String sql = "UPDATE rules SET last_alert_time = ? WHERE user_id = ? AND id = ?";
        try (Connection c = DriverManager.getConnection(dbUrl);
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, nowMillis);
            ps.setLong(2, userId);
            ps.setLong(3, ruleId);
            return ps.executeUpdate() > 0;
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to update last_alert_time", e);
        }
    }

    private SpreadRule fromRow(ResultSet rs) throws SQLException {
        long id = rs.getLong("id");
        long userId = rs.getLong("user_id");
        String formula = rs.getString("formula");
        Double upper = rs.getObject("upper_bound") == null ? null : rs.getDouble("upper_bound");
        Double lower = rs.getObject("lower_bound") == null ? null : rs.getDouble("lower_bound");
        long lastAlertTime = rs.getLong("last_alert_time");
        return new SpreadRule(id, userId, formula, upper, lower, lastAlertTime);
    }
}

