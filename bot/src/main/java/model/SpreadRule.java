package model;

public class SpreadRule {
    private long id;
    private long userId;
    private String formula;
    private Double upperBound;
    private Double lowerBound;
    private long lastAlertTimeMillis;

    public SpreadRule(long id, long userId, String formula, Double upperBound, Double lowerBound, long lastAlertTimeMillis) {
        this.id = id;
        this.userId = userId;
        this.formula = formula;
        this.upperBound = upperBound;
        this.lowerBound = lowerBound;
        this.lastAlertTimeMillis = lastAlertTimeMillis;
    }

    public long getId() {
        return id;
    }

    public long getUserId() {
        return userId;
    }

    public String getFormula() {
        return formula;
    }

    public Double getUpperBound() {
        return upperBound;
    }

    public Double getLowerBound() {
        return lowerBound;
    }

    public long getLastAlertTimeMillis() {
        return lastAlertTimeMillis;
    }

    public void setUpperBound(Double upperBound) {
        this.upperBound = upperBound;
    }

    public void setLowerBound(Double lowerBound) {
        this.lowerBound = lowerBound;
    }

    public void setLastAlertTimeMillis(long lastAlertTimeMillis) {
        this.lastAlertTimeMillis = lastAlertTimeMillis;
    }
}

